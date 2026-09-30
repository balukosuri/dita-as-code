#!/usr/bin/env python3
"""DAC blocker generator - cards and copy-ready request messages.

Reads detect.json and probe.json, emits:
  <root>/.dac/state/blockers.json          machine-readable, consumed by report.py
  <root>/.dac/blockers/BLK-<id>.md         one card per blocker
  <root>/.dac/blockers/BLK-<id>-request.md a message the writer can paste and send

Two rules are enforced here rather than left to judgement:
  - Degrade before defer. Anything with a working fallback is reported as degraded, never
    as blocked. Conflating them makes a successful run look like a failure.
  - Every blocker has a lane, an owner role and a "meanwhile". A blocker the writer cannot
    act on today must still leave them something to do.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

DAC_VERSION = "0.1.0"

CARD_WIDTH = 70

# Impact ranking. Only the top three are surfaced in the run report; the rest live in files,
# because a report with fourteen blockers gets ignored.
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def load_state(path, what):
    """Read a DAC state file, failing with an instruction rather than a traceback."""
    if not os.path.isfile(path):
        raise SystemExit(
            "error: %s not found.\n"
            "       Run the audit first:  dac audit\n"
            "       (expected at %s)" % (what, path))
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        raise SystemExit(
            "error: %s is corrupt and cannot be read.\n"
            "       This usually means a previous run was interrupted.\n"
            "       Delete the .dac/state directory and run the audit again:\n"
            "         rm -rf .dac/state && dac audit\n"
            "       (file: %s)" % (what, path))
    except OSError as exc:
        raise SystemExit("error: cannot read %s: %s" % (path, exc))


def wrap(text, width, indent):
    """Minimal greedy wrapper. Avoids textwrap so card layout stays fully explicit."""
    words = (text or "").split()
    lines, cur = [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    if not lines:
        return [""]
    return [lines[0]] + [" " * indent + line for line in lines[1:]]


def field(label, text, label_w=12, total=CARD_WIDTH):
    body = wrap(text, total - label_w, label_w)
    out = ["%-*s%s" % (label_w, label, body[0])]
    out.extend(body[1:])
    return out


# --------------------------------------------------------------------------------------
# Blocker catalogue
# --------------------------------------------------------------------------------------


def blk(bid, title, severity, lane, what, why, who, fix, meanwhile,
        cost="None.", time="", request=None, degraded_alternative=None):
    return {
        "id": bid, "title": title, "severity": severity, "lane": lane,
        "what": what, "impact": what, "why": why, "who": who, "fix": fix,
        "meanwhile": meanwhile, "cost": cost, "time": time,
        "request": request, "degraded_alternative": degraded_alternative,
    }


def runtime_blockers(prb):
    caps = prb.get("capabilities", {})
    runtime = {r["name"]: r for r in prb.get("runtime", [])}
    egress = {e["id"]: e for e in prb.get("egress", [])}
    out = []

    java = runtime.get("java", {})
    docker = runtime.get("docker", {})

    if not caps.get("has_any_build_path"):
        reasons = []
        if not java.get("present"):
            reasons.append("there is no Java runtime on PATH")
        elif java.get("status") == "too-old":
            reasons.append("the installed Java is older than 17")
        if docker.get("present") and docker.get("status") == "client-only":
            reasons.append("the Docker client is installed but its daemon is not running")
        elif not docker.get("present"):
            reasons.append("Docker is not installed")
        if caps.get("can_download_dita_ot"):
            reasons.append("DITA-OT itself downloads fine, so this is a runtime problem rather "
                           "than a network one")
        why = "; ".join(reasons) or "no runtime and no container available"
        why = why[:1].upper() + why[1:] + "."
        out.append(blk(
            "BLK-no-build-path",
            "Nothing can build DITA output yet",
            "critical", "green",
            "You cannot build or validate documentation locally at all, which means none of the "
            "rest of the pipeline can be proven to work on your machine.",
            why,
            "You, on your own machine. No permission needed.",
            "Pick whichever is easier. Native: install Temurin 17, then DITA-OT 4.4.1. On macOS "
            "that is 'brew install --cask temurin@17'. Do NOT run a bare 'brew install dita-ot' - "
            "it pulls a much newer JDK than the toolkit is tested against. Container: start "
            "Docker and DAC will use ghcr.io/dita-ot/dita-ot:4.4.1 instead.",
            "CI can still validate and build for you on every pull request, so you are not "
            "blocked from contributing. You just cannot check your work before pushing.",
            time="About 10 minutes.",
        ))
    elif not caps.get("can_build_native") and caps.get("can_build_container"):
        out.append(blk(
            "BLK-container-only",
            "Builds will run in a container rather than natively",
            "info", "green",
            "Builds work, but through Docker, which is slower to start and means Vale cannot "
            "lint your .dita files locally.",
            "There is no usable local Java with DITA-OT, but Docker and ghcr.io are both "
            "available.",
            "You, if you want the faster path. Nothing is required.",
            "Install Temurin 17 and DITA-OT 4.4.1 whenever convenient.",
            "Nothing is missing from the pipeline. Prose linting still runs in CI.",
            degraded_alternative="Container builds via ghcr.io/dita-ot/dita-ot:4.4.1",
        ))

    if java.get("status") == "ahead-of-tested":
        out.append(blk(
            "BLK-java-version",
            "Java is newer than DITA-OT is tested against",
            "low", "green",
            "Builds may work, or may fail in ways whose error messages point at Ant or Saxon "
            "rather than at the real cause.",
            "Java %s is installed. DITA-OT 4.4.x is built and tested against 17 to 21, and "
            "DITA-OT's own CI pins Temurin 17." % (java.get("major") or "?"),
            "You. Installing a second JDK alongside this one is safe.",
            "Install Temurin 17 and point JAVA_HOME at it for docs builds.",
            "Try building as-is. If it works, nothing needs doing - just remember this note if "
            "you later hit an unexplained build error.",
            degraded_alternative="Proceeding on the installed JDK and recording the risk",
        ))

    vale = runtime.get("vale", {})
    if vale.get("present") and not caps.get("can_lint_prose_dita"):
        out.append(blk(
            "BLK-no-prose-lint",
            "Vale cannot lint DITA files on this machine",
            "low", "green",
            "Style and terminology checks will not run locally. They still run in CI.",
            "Vale supports DITA by driving the 'dita' command internally and linting the "
            "resulting HTML, so it needs DITA-OT on PATH and therefore Java.",
            "You. Same fix as the build runtime.",
            "Install Temurin 17 and DITA-OT, and Vale will pick DITA up automatically.",
            "Prose linting runs in CI on every pull request, so nothing reaches the published "
            "docs unchecked.",
            degraded_alternative="Prose linting in CI only",
        ))
    if vale.get("status") == "below-floor":
        out.append(blk(
            "BLK-vale-below-floor",
            "Vale is too old to support DITA ignore patterns",
            "low", "green",
            "You cannot suppress a false positive in a DITA file, so a rule that misfires has to "
            "be disabled entirely rather than ignored in one place.",
            "Vale %s is installed. TokenIgnores and BlockIgnores only work on DITA from 3.22.0 "
            "onward." % (vale.get("version") or "?"),
            "You. It is a single upgrade command.",
            "Upgrade Vale: 'brew upgrade vale', or download 3.22.0 or later.",
            "The rules still run. You just have a blunter instrument for exceptions.",
            degraded_alternative="Running Vale without DITA ignore patterns",
        ))

    if not caps.get("can_normalise_xml"):
        why = "Node is not installed." if not runtime.get("node", {}).get("present") else \
            "The npm registry is not reachable: %s." % egress.get("npm-registry", {}).get(
                "verdict", "unknown")
        out.append(blk(
            "BLK-no-xml-formatter",
            "XML formatting cannot be installed",
            "medium", "yellow",
            "DITA diffs in pull requests will stay noisy and hard to review. This is the single "
            "most common reason teams conclude that DITA and docs-as-code do not mix - and it is "
            "solvable, which makes it worth chasing.",
            why,
            "You, if it is just Node. Whoever manages network or proxy policy, if the npm "
            "registry is blocked.",
            "Install Node 20 or later. If npm is blocked, ask for registry.npmjs.org to be "
            "allowed, or point npm at your internal registry mirror.",
            "Everything else works. Reviewers will need to read raw XML diffs until this is "
            "fixed, so keep pull requests small in the meantime.",
            request={
                "subject": "Allow access to the npm registry for documentation tooling",
                "setting": "network or proxy allow-list entry for registry.npmjs.org, or the URL "
                           "of our internal npm mirror",
                "what": "It lets us install a formatter that makes our XML documentation "
                        "readable in code review.",
                "access": "Read-only package downloads. No credentials or data are sent.",
                "why": "Without it, reviewing documentation changes is slow and error-prone, "
                       "because every change looks larger than it is.",
            },
        ))

    maven = egress.get("maven-central", {})
    if maven.get("verdict") == "policy-denied":
        out.append(blk(
            "BLK-maven-denied",
            "Maven Central is blocked by network policy",
            "medium", "yellow",
            "Any Gradle-based DITA build will fail, and the failure looks like a random network "
            "error rather than a policy decision - which is how teams lose a day to it.",
            maven.get("detail", "An artifact proxy or web filter denied the request."),
            "Whoever manages your artifact proxy or network policy.",
            "Either request the Maven Central mirror path be allowed, or point the build at your "
            "internal artifact proxy. DAC will prefer the plain DITA-OT command-line path over "
            "Gradle so this does not block you.",
            "DAC uses the DITA-OT CLI rather than Gradle, so your pipeline works regardless. "
            "This only matters if you later want Gradle's build caching.",
            degraded_alternative="DITA-OT CLI build path instead of Gradle",
            request={
                "subject": "Allow Maven Central access for documentation builds",
                "setting": "artifact proxy rule permitting repo1.maven.org, or the internal "
                           "mirror URL we should use instead",
                "what": "It lets our documentation build resolve the libraries it needs.",
                "access": "Read-only downloads of open-source libraries.",
                "why": "Without it our documentation build fails with a confusing network error.",
            },
        ))
    return out


def vendor_blockers(det, prb):
    vendors = {f["vendor"]: f for f in det.get("findings", [])
               if f["confidence"] in ("high", "medium")}
    vprobe = {v.get("vendor"): v for v in prb.get("vendor", [])}
    out = []

    if "oxygen" in vendors and not vprobe.get("oxygen", {}).get("scripting_licensed", False):
        out.append(blk(
            "BLK-oxygen-scripting",
            "No Oxygen Scripting licence, so no headless Oxygen validation",
            "medium", "red",
            "You cannot run Oxygen's 'Validate and Check For Completeness' in CI. That is the "
            "most thorough DITA link and completeness check available anywhere.",
            "Oxygen Scripting is a separate commercial purchase, and no "
            "scriptinglicensekey.txt was found in the installation directory.",
            "Whoever owns tooling budget, plus your Oxygen account contact.",
            "Purchase an Oxygen Scripting licence, or request a trial key from "
            "sales@oxygenxml.com to evaluate it first.",
            "DAC has installed the free equivalent: DITA-OT validate, xmllint with an XML "
            "catalog, and Schematron via a free CLI. This catches grammar errors, broken links "
            "and house-rule violations. It does not catch everything Oxygen's completeness check "
            "does.",
            cost="Quote only from Syncro Soft. Note that Publishing Engine, WebHelp and PDF "
                 "Chemistry are three further separate purchases.",
            degraded_alternative="DITA-OT validate, xmllint with catalog, and SchXslt",
            request={
                "subject": "Oxygen Scripting licence for automated documentation checks",
                "setting": "an Oxygen Scripting licence, or a trial key from sales@oxygenxml.com",
                "what": "It lets our documentation checks run automatically on a server instead "
                        "of someone running them by hand in the editor.",
                "access": "A licence key file placed in the Oxygen installation directory.",
                "why": "It is the most thorough check available for broken links and incomplete "
                       "content in our documentation. We have a free partial substitute running "
                       "now, but it does not catch everything.",
            },
        ))

    if "heretto" in vendors:
        out.append(blk(
            "BLK-heretto-v1-api",
            "Heretto content export is not running",
            "high", "yellow",
            "The nightly CCMS-to-Git sync. Without it your repository has validation and CI set "
            "up but no content to run them against.",
            "The Heretto v2 API covers publishing only and is self-labelled Alpha. The v1 "
            "endpoints that actually read content are real, but their documentation is available "
            "only on request.",
            "Your Heretto Customer Success Manager. NOT a Heretto administrator - this is a "
            "documentation and configuration request, not a permissions change. Sending it to an "
            "admin will just get it forwarded.",
            "Ask your CSM for the v1 API documentation, and to enable webhooks in NotifyPull "
            "mode for your organisation. NotifyPull is the sanctioned way to pull DITA source "
            "out.",
            "Export one map manually from the Content Library - right-click, then Download, then "
            "File + Dependencies - and drop it into src/. That lets you exercise the whole "
            "validate, build and publish chain today and see it working.",
            time="About 5 minutes for them once they read the message.",
            request={
                "subject": "Request: Heretto v1 API documentation and webhook enablement",
                "setting": "documentation for the v1 'Get Document Contents' and 'Get Document "
                           "Information' endpoints, and webhooks enabled in NotifyPull mode for "
                           "our organisation",
                "what": "It lets our documentation be automatically copied into our version "
                        "control system every night.",
                "access": "Read-only. We are only reading content out; nothing is written back "
                          "into the CCMS.",
                "why": "It gives us automated quality checks, a full change history and a "
                       "disaster-recovery copy of our content, without changing how anyone "
                       "authors in Heretto.",
            },
        ))

    if "paligo" in vendors:
        out.append(blk(
            "BLK-paligo-admin",
            "Paligo API access needs an administrator account",
            "high", "yellow",
            "Automated export from Paligo. There is no partial version of this.",
            "Paligo's documentation states that the API user must be an admin user, with no "
            "exceptions, and licence permissions carry into the API - so a non-admin key cannot "
            "be made to work. This is a hard wall rather than something to degrade around.",
            "A Paligo administrator. Only admins can create API keys, and an admin can only see "
            "keys they created themselves.",
            "Ask a Paligo administrator to generate an API key for automation, or to run the "
            "export on a schedule on your behalf.",
            "Separately and importantly: Paligo content is DocBook 5.1, not DITA. Converting it "
            "to DITA is genuine XSLT work that DAC scopes but does not perform. Read the "
            "DocBook note in dac-audit.md before planning any of this.",
            request={
                "subject": "Request: Paligo API key for automated documentation export",
                "setting": "an API key generated under the admin account, since Paligo requires "
                           "admin rights for API access",
                "what": "It lets us take an automated nightly copy of our documentation source "
                        "into version control.",
                "access": "Read-only use. We are exporting content, not modifying it.",
                "why": "It gives us a change history and a recoverable backup of our content.",
            },
        ))

    if "aem-guides" in vendors:
        out.append(blk(
            "BLK-aem-oauth",
            "AEM Guides needs Adobe IMS credentials",
            "high", "yellow",
            "Automated export from AEM Guides.",
            "AEM Cloud authentication is Adobe IMS OAuth Server-to-Server, requiring a Bearer "
            "token plus an X-Api-Key. These are provisioned in the Adobe Developer Console, not "
            "in AEM itself, so they cannot be self-served from the authoring environment.",
            "Whoever owns your Adobe Developer Console - usually IT or a platform team rather "
            "than the documentation team.",
            "Ask them to create Server-to-Server OAuth credentials for the AEM Guides API and "
            "share the client ID and secret.",
            "Two things to settle while you wait, both of which change the design. First, AEM "
            "Guides defaults to a CSS-based Native PDF engine rather than DITA-OT, so a local "
            "build will never match the reference PDF - decide which is authoritative. Second, "
            "if you are on a UUID build, link checking needs a UUID-aware checker.",
            request={
                "subject": "Request: Adobe IMS Server-to-Server credentials for AEM Guides API",
                "setting": "OAuth Server-to-Server credentials for the AEM Guides API, created "
                           "in the Adobe Developer Console",
                "what": "It lets our documentation be automatically copied into version control "
                        "for automated checking.",
                "access": "Read-only access to documentation assets.",
                "why": "It gives us automated quality checks and a change history for our "
                       "documentation.",
            },
        ))

    if "arbortext" in vendors and "E" in vendors["arbortext"].get("archetype", []):
        out.append(blk(
            "BLK-pe-allowlist",
            "Arbortext Publishing Engine may not permit your function call",
            "medium", "yellow",
            "Publishing through Arbortext PE, which would give output identical to what authors "
            "see today.",
            "PE access is governed by the AllowedFunctions allowlist in e3config.xml. Valid "
            "credentials calling a function that is not allowlisted still fail, so this is not a "
            "credentials problem.",
            "The administrator who maintains e3config.xml on the PE server.",
            "Ask them to confirm which ClientFunction patterns are allowlisted, and to permit "
            "the publishing call if it is not already allowed.",
            "DAC has wired publishing through local DITA-OT instead. Be aware the output will "
            "differ from Arbortext-composed PDF by design, because PE composes via the Arbortext "
            "Formatting Engine rather than DITA-OT - this is not version drift and cannot be "
            "tuned away.",
            degraded_alternative="Local DITA-OT publishing, with different PDF output",
        ))

    if "madcap-flare" in vendors:
        out.append(blk(
            "BLK-flare-floating-licence",
            "Flare will deactivate itself on an ephemeral CI runner",
            "medium", "red",
            "Unattended automated builds on cloud CI.",
            "Flare deactivates when a virtual machine's hardware fingerprint changes, so builds "
            "fail with an inactivated-licence error even though Flare was activated the day "
            "before. The vendor fix, 'madbuild -activate', is available only on enterprise "
            "floating licences and needs a license.json in the Flare Desktop.app folder.",
            "Whoever owns MadCap licensing.",
            "Obtain an enterprise floating licence, or use a pinned, non-ephemeral Windows "
            "runner whose hardware identity does not change.",
            "Use a dedicated Windows build machine rather than a cloud runner. Also add an "
            "antivirus exclusion for the Output folder - scanning it mid-build is a documented "
            "cause of build failures.",
            cost="An enterprise floating licence costs more than the standard build licence. "
                 "Quote-gated.",
            degraded_alternative="A pinned non-ephemeral Windows runner",
        ))

    if "zoomin" in vendors:
        out.append(blk(
            "BLK-zoomin-sunset",
            "Zoomin is being wound down - do not build on it",
            "high", "yellow",
            "A long-term delivery target. DAC has deliberately not wired a publish step to "
            "Zoomin.",
            "Salesforce completed its acquisition in November 2024 and ended renewals on "
            "1 September 2025 for the documentation portal, In-Product Help, the API and "
            "Headless products. Existing contracts are being honoured, in some cases into 2026.",
            "Whoever owns the Zoomin contract, and whoever will choose its replacement.",
            "Confirm your contract end date and start evaluating a replacement. Fluid Topics "
            "ships a Zoomin connector, which makes it a plausible migration path.",
            "Your DITA source and build pipeline are completely independent of the delivery "
            "platform. That is the point of this architecture: switching delivery targets later "
            "is a configuration change, not a migration.",
        ))
    return out


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def render_card(b):
    rule = "-" * CARD_WIDTH
    L = ["%s - %s" % (b["id"], b["title"]), rule]
    L += field("WHAT'S", b["what"])
    L += field("MISSING", "")
    L.append("")
    L += field("WHY", b["why"])
    L.append("")
    L += field("WHO", b["who"])
    L.append("")
    L += field("FIX", b["fix"])
    L.append("")
    if b.get("request"):
        L += field("DRAFT", "A ready-to-send message is at "
                            ".dac/blockers/%s-request.md" % b["id"])
        L += field("MESSAGE", "")
        L.append("")
    L += field("MEANWHILE", b["meanwhile"])
    L.append("")
    L += field("COST", b["cost"])
    if b.get("time"):
        L += field("TIME", b["time"])
    L += field("LANE", b["lane"])
    L.append(rule)
    # Strip the placeholder continuation lines produced by the two-line labels.
    return "\n".join(x for x in L if x.strip() not in ("MISSING", "MESSAGE"))


def render_request(b):
    r = b["request"]
    return """# %s

Hi,

I'm setting up automated checking and publishing for our documentation, so that it builds
and validates itself whenever we make a change.

To finish, I need one thing: **%s**.

**What it does:** %s

**Access level:** %s

**Why it matters:** %s

If it's easier to do this on a call, I'm happy to walk through it.

Thanks

---
*Generated by the DITA-as-Code Kit for blocker %s. Edit freely before sending.*
""" % (r["subject"], r["setting"], r["what"], r["access"], r["why"], b["id"])


def run(root):
    state = os.path.join(root, ".dac", "state")
    det = load_state(os.path.join(state, "detect.json"), "detection results (detect.json)")
    prb = load_state(os.path.join(state, "probe.json"), "capability probe results (probe.json)")

    found = runtime_blockers(prb) + vendor_blockers(det, prb)

    # Degrade before defer: anything with a working fallback is a degraded step, not a
    # blocker. Reporting it as blocked makes a successful run look like a failure.
    blockers = [b for b in found if not b.get("degraded_alternative")]
    degraded = [b for b in found if b.get("degraded_alternative")]

    blockers.sort(key=lambda b: SEVERITY_RANK.get(b["severity"], 9))

    outdir = os.path.join(root, ".dac", "blockers")
    os.makedirs(outdir, exist_ok=True)
    written = []
    for b in blockers + degraded:
        card = os.path.join(outdir, "%s.md" % b["id"])
        with open(card, "w", encoding="utf-8") as fh:
            fh.write("```\n" + render_card(b) + "\n```\n")
        written.append(card)
        if b.get("request"):
            rp = os.path.join(outdir, "%s-request.md" % b["id"])
            with open(rp, "w", encoding="utf-8") as fh:
                fh.write(render_request(b))
            b["draft_message_path"] = ".dac/blockers/%s-request.md" % b["id"]
            written.append(rp)

    payload = {
        "dac_version": DAC_VERSION,
        "stage": "blockers",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": os.path.abspath(root),
        "blocked": blockers,
        "degraded": degraded,
        "surfaced": [b["id"] for b in blockers[:3]],
        "files": [os.path.relpath(p, root) for p in written],
    }
    with open(os.path.join(state, "blockers.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, indent=2) + "\n")
    return payload


def main(argv=None):
    ap = argparse.ArgumentParser(description="DAC blocker card generator")
    ap.add_argument("--root", default=".")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    res = run(args.root)
    if not args.quiet:
        print("blockers: %d blocked, %d degraded" % (len(res["blocked"]), len(res["degraded"])),
              file=sys.stderr)
        for b in res["blocked"]:
            star = "*" if b["id"] in res["surfaced"] else " "
            print(" %s %-9s %-6s %s" % (star, b["severity"], b["lane"], b["id"]), file=sys.stderr)
        for b in res["degraded"]:
            print("   degraded        %-28s -> %s" % (b["id"], b["degraded_alternative"]),
                  file=sys.stderr)
        print("  (* = surfaced in the run report; all cards written to .dac/blockers/)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
