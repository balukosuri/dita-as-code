#!/usr/bin/env python3
"""DAC prober - what can THIS seat actually do?

Capability varies per seat, not per product. Two Oxygen users at the same company have
different powers depending on whether anyone bought a Scripting licence. A capability
database is necessary but never sufficient, so this probes reality.

Three probe classes:
  runtime  - Java version range, DITA-OT, Vale floor, Docker, Node, xmllint, git
  egress   - Maven Central, GitHub releases, ghcr.io, DITA-OT plugin registry
  vendor   - credentialed, read-only, only when keys are supplied

All probes are read-only. Nothing is installed, nothing is written to the target tree.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

DAC_VERSION = "0.1.0"

# Versions verified 18 September 2026.
DITA_OT_CURRENT = "4.4.1"
JAVA_MIN = 17                  # DITA-OT 4.4.x is designed for and tested against Java 17+
JAVA_TESTED_MAX = 21           # beyond this you are ahead of what the toolkit is tested on
VALE_DITA_IGNORES_FLOOR = (3, 22, 0)   # TokenIgnores/BlockIgnores for DITA need 3.22.0+

HTTP_TIMEOUT = 12
USER_AGENT = "dac-probe/%s" % DAC_VERSION


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------


def run_cmd(args, timeout=25):
    """Run a command, returning (ok, combined_output). Never raises."""
    try:
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=timeout)
        return proc.returncode == 0, proc.stdout.decode("utf-8", errors="replace").strip()
    except FileNotFoundError:
        return False, "not found"
    except subprocess.TimeoutExpired:
        return False, "timed out after %ss" % timeout
    except OSError as exc:
        return False, str(exc)


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))


def vtuple_str(v):
    return ".".join(str(p) for p in v) if v else None


def finding(name, present, **kw):
    out = {"name": name, "present": bool(present)}
    out.update(kw)
    return out


# --------------------------------------------------------------------------------------
# runtime probes
# --------------------------------------------------------------------------------------


def probe_java():
    exe = shutil.which("java")
    if not exe:
        return finding(
            "java", False,
            detail="No Java runtime on PATH.",
            impact="DITA-OT cannot run natively. Vale cannot lint .dita files either, because "
                   "Vale shells out to the dita command. This is the root of the dependency graph.",
            degrade="Use the container path: ghcr.io/dita-ot/dita-ot:%s" % DITA_OT_CURRENT,
            blocker_hint="BLK-java")
    ok, out = run_cmd([exe, "-version"])
    # macOS ships a stub that exits non-zero with a "Unable to locate a Java Runtime" message.
    if not ok and "unable to locate a java runtime" in out.lower():
        return finding(
            "java", False, path=exe,
            detail="java on PATH is the macOS stub, not a real JDK.",
            impact="DITA-OT cannot run natively; Vale cannot lint .dita.",
            degrade="Use ghcr.io/dita-ot/dita-ot:%s, or install Temurin 17." % DITA_OT_CURRENT,
            blocker_hint="BLK-java")
    ver = parse_version(out)
    major = ver[0] if ver else None
    # Java 9+ reports as 9.x/17.x/21.x; legacy reports 1.8.x.
    if major == 1 and ver:
        major = ver[1]
    res = finding("java", True, path=exe, version=vtuple_str(ver), major=major, raw=out.splitlines()[0]
                  if out else None)
    if major is None:
        res["status"] = "unknown"
    elif major < JAVA_MIN:
        res["status"] = "too-old"
        res["impact"] = ("DITA-OT %s requires Java %d or later. This JDK is %s."
                         % (DITA_OT_CURRENT, JAVA_MIN, major))
        res["blocker_hint"] = "BLK-java-version"
    elif major > JAVA_TESTED_MAX:
        res["status"] = "ahead-of-tested"
        res["impact"] = ("Java %s is newer than the range DITA-OT is built and tested against "
                         "(%d-%d). Builds may work, or fail opaquely inside Ant or Saxon. "
                         "Homebrew's dita-ot formula depends on plain 'openjdk', which is how "
                         "teams end up here by accident." % (major, JAVA_MIN, JAVA_TESTED_MAX))
        res["degrade"] = "Pin Temurin 17, which is what DITA-OT's own CI uses."
    else:
        res["status"] = "ok"
    return res


def probe_dita_ot():
    exe = shutil.which("dita")
    home = os.environ.get("DITA_HOME")
    if not exe and not home:
        return finding(
            "dita-ot", False,
            detail="No dita command on PATH and DITA_HOME is unset.",
            impact="No local build, no local validation, and Vale cannot lint .dita files.",
            degrade="Container path, or install DITA-OT %s." % DITA_OT_CURRENT,
            blocker_hint="BLK-dita-ot")
    ok, out = run_cmd([exe or os.path.join(home, "bin", "dita"), "--version"])
    ver = parse_version(out)
    res = finding("dita-ot", ok, path=exe, dita_home=home, version=vtuple_str(ver), raw=out[:200])
    if ver:
        cur = parse_version(DITA_OT_CURRENT)
        res["current_release"] = DITA_OT_CURRENT
        if ver < cur:
            res["status"] = "behind"
            res["impact"] = ("Local DITA-OT is %s; current release is %s."
                             % (vtuple_str(ver), DITA_OT_CURRENT))
        else:
            res["status"] = "ok"
        if ver < (4, 4, 0):
            res["notes"] = ["--deliverable became repeatable only in 4.4, and 4.4 routed DITA 1.x "
                            "chunking through the DITA 2.0 module, which may change generated file "
                            "names for splitting operations."]
    return res


def probe_vale():
    exe = shutil.which("vale")
    if not exe:
        return finding(
            "vale", False,
            detail="Vale is not installed.",
            impact="No prose linting.",
            degrade="brew install vale, or skip editorial gates and keep structural validation.")
    ok, out = run_cmd([exe, "--version"])
    ver = parse_version(out)
    res = finding("vale", ok, path=exe, version=vtuple_str(ver), raw=out[:120])
    res["notes"] = [
        "Vale supports .dita natively, but it works by shelling out to the dita command with the "
        "html5 transform and linting the result - so it requires DITA-OT on PATH, and therefore "
        "Java.",
        ".ditamap is NOT a supported extension. Map-level prose goes unlinted; do not report "
        "coverage you do not have.",
        "Never add a [formats] section mapping dita - it silently breaks native DITA handling. "
        "Scope config to [*.dita] only.",
    ]
    if ver and ver < VALE_DITA_IGNORES_FLOOR:
        res["status"] = "below-floor"
        res["impact"] = ("Vale %s predates %s, so TokenIgnores and BlockIgnores do not work for "
                         "DITA. Style exceptions cannot be suppressed."
                         % (vtuple_str(ver), vtuple_str(VALE_DITA_IGNORES_FLOOR)))
        res["degrade"] = "Upgrade Vale, or accept that ignore patterns will not apply to DITA."
    elif ver:
        res["status"] = "ok"
    return res


def probe_simple(name, exe, args, notes=None):
    path = shutil.which(exe)
    if not path:
        return finding(name, False, detail="%s not on PATH." % exe)
    ok, out = run_cmd([path] + args)
    res = finding(name, ok, path=path, version=vtuple_str(parse_version(out)),
                  raw=(out.splitlines() or [""])[0][:160])
    if notes:
        res["notes"] = notes
    return res


def probe_docker():
    path = shutil.which("docker")
    if not path:
        return finding("docker", False, detail="Docker not on PATH.",
                       impact="No container fallback if Java is unavailable.")
    ok, out = run_cmd([path, "--version"])
    # A present client with a dead daemon is a common and confusing state.
    running, _ = run_cmd([path, "info", "--format", "{{.ServerVersion}}"], timeout=20)
    res = finding("docker", ok, path=path, version=vtuple_str(parse_version(out)),
                  daemon_running=running, raw=out[:120])
    if ok and not running:
        res["status"] = "client-only"
        res["impact"] = ("The Docker client is installed but the daemon is not responding, so the "
                         "container fallback is not usable right now.")
    elif ok:
        res["status"] = "ok"
        res["notes"] = ["Use ghcr.io/dita-ot/dita-ot - NOT ditaot/dita-ot on Docker Hub, which was "
                        "abandoned years ago with a newest tag of 2.5.3."]
    return res


def probe_runtime():
    return [
        probe_java(),
        probe_dita_ot(),
        probe_docker(),
        probe_vale(),
        probe_simple("git", "git", ["--version"]),
        probe_simple("node", "node", ["--version"],
                     notes=["Needed for @prettier/plugin-xml, husky and lint-staged - the XML "
                            "diff normalisation chain."]),
        probe_simple("npm", "npm", ["--version"]),
        probe_simple("xmllint", "xmllint", ["--version"],
                     notes=["Usable for well-formedness and DTD validation, but NOT a dependable "
                            "RELAX NG validator - which matters because DITA 2.0 grammars and the "
                            "DITA-OT project.rnc schema are RNG. Use jing for those."]),
        probe_simple("jing", "jing", ["-version"]),
        probe_simple("gh", "gh", ["--version"]),
        probe_simple("python3", "python3", ["--version"]),
    ]


# --------------------------------------------------------------------------------------
# egress probes
# --------------------------------------------------------------------------------------


# Markers that mean an artifact proxy actively DENIED the request, as distinct from
# transparently mirroring it. A host change alone is not evidence of a block: GitHub
# release assets legitimately move to its own CDN, and a corporate Artifactory commonly
# mirrors Maven Central and npm and serves them perfectly well.
DENY_MARKERS = ("package-reroute", "action=deny", "reasoncode=", "blockpage", "access-denied")


EGRESS_TARGETS = [
    {
        "id": "github-releases",
        "url": "https://github.com/dita-ot/dita-ot/releases/download/%s/dita-ot-%s.zip"
               % (DITA_OT_CURRENT, DITA_OT_CURRENT),
        "why": "Downloading the pinned DITA-OT distribution.",
        "on_block": "DITA-OT cannot be installed from GitHub. Fall back to the container image or "
                    "an internal mirror.",
        "range": True,
        # Release assets legitimately redirect to GitHub's own asset CDN.
        "cdn_hosts": ("githubusercontent.com", "github.io", "amazonaws.com"),
    },
    {
        "id": "maven-central",
        "url": "https://repo1.maven.org/maven2/net/sf/saxon/Saxon-HE/maven-metadata.xml",
        "why": "Gradle-based DITA builds and Schematron CLI jars resolve from Maven Central.",
        "on_block": "Any Gradle DITA build that declares mavenCentral() will fail, and the failure "
                    "looks like a network flake rather than a policy block. Route through the "
                    "internal artifact proxy, or avoid the Gradle path entirely.",
        "range": True,
    },
    {
        "id": "ghcr",
        "url": "https://ghcr.io/v2/",
        "why": "Pulling ghcr.io/dita-ot/dita-ot - the no-Java fallback.",
        "on_block": "The container fallback is unavailable. If Java is also missing, there is no "
                    "local build path at all.",
        "accept_status": (200, 401),   # 401 is the normal unauthenticated response
    },
    {
        "id": "dita-ot-registry",
        # The browsable index lives at dita-ot.org/plugins but is backed by the
        # dita-ot/registry repo, which is what resolving a plugin ID actually reads.
        "url": "https://raw.githubusercontent.com/dita-ot/registry/master/org.lwdita.json",
        "cdn_hosts": ("githubusercontent.com",),
        "why": "Installing DITA-OT plugins by ID.",
        "on_block": "Plugins must be installed from a local zip or an internal registry. DITA-OT "
                    "supports private registries via the 'registry' key in "
                    "config/configuration.properties.",
    },
    {
        "id": "npm-registry",
        "url": "https://registry.npmjs.org/@prettier/plugin-xml",
        "why": "Installing the XML formatter that makes DITA diffs reviewable.",
        "on_block": "XML diff normalisation cannot be installed from npm. Without it, PR review of "
                    "DITA source stays painful.",
    },
]


def http_probe(target):
    url = target["url"]
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", USER_AGENT)
    if target.get("range"):
        req.add_header("Range", "bytes=0-256")
    ctx = ssl.create_default_context()
    result = {"id": target["id"], "url": url, "why": target["why"]}
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT, context=ctx) as resp:
            status = resp.status
            final = resp.geturl()
            body = resp.read(512)
        result.update(status=status, final_url=final)
        accept = target.get("accept_status", (200, 206, 204))
        denied = (any(m in final.lower() for m in DENY_MARKERS)
                  or any(m.encode() in body.lower() for m in DENY_MARKERS))
        if denied:
            result.update(reachable=False, verdict="policy-denied",
                          detail="An artifact proxy or web filter denied this request - the "
                                 "response carries a denial marker. This is policy, not a network "
                                 "fault, and it will not resolve by retrying.",
                          on_block=target["on_block"])
        elif status in accept or 200 <= status < 300:
            proxied = (_registrable(final) != _registrable(url)
                       and _registrable(final) not in target.get("cdn_hosts", ()))
            result.update(reachable=True, verdict="proxied-ok" if proxied else "ok")
            if proxied:
                result["proxied_via"] = _host(final)
                result["detail"] = (
                    "Reachable, but served from %s rather than the origin. If that is a corporate "
                    "artifact proxy, point CI at it explicitly. Note that such proxies often allow "
                    "most paths while denying specific artifacts or categories, so a passing probe "
                    "does not guarantee every dependency resolves." % _host(final))
        else:
            result.update(reachable=False, verdict="http-%s" % status,
                          on_block=target["on_block"])
    except urllib.error.HTTPError as exc:
        accept = target.get("accept_status", ())
        if exc.code in accept:
            result.update(status=exc.code, reachable=True, verdict="ok",
                          detail="HTTP %s is the expected unauthenticated response." % exc.code)
        else:
            result.update(status=exc.code, reachable=False, verdict="http-%s" % exc.code,
                          on_block=target["on_block"])
    except urllib.error.URLError as exc:
        reason = str(getattr(exc, "reason", exc))
        verdict = "tls-error" if "certificate" in reason.lower() else "unreachable"
        result.update(reachable=False, verdict=verdict, detail=reason,
                      on_block=target["on_block"])
        if verdict == "tls-error":
            result["detail"] += (" - a TLS interception proxy is likely. The corporate root CA "
                                 "may need to be trusted by the JDK and by Node.")
    except Exception as exc:  # noqa: BLE001 - a probe must never crash the run
        result.update(reachable=False, verdict="error", detail=str(exc),
                      on_block=target["on_block"])
    return result


def _host(url):
    m = re.match(r"https?://([^/:]+)", url or "")
    return m.group(1).lower() if m else ""


def _registrable(url):
    """Last two labels of the host, so github.com and githubusercontent.com differ but
    api.github.com and github.com do not. Crude but sufficient to tell 'same provider
    redirected me to its CDN' from 'something else answered'."""
    parts = _host(url).split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else _host(url)


def probe_egress(skip=False):
    if skip:
        return [{"id": t["id"], "url": t["url"], "reachable": None, "verdict": "skipped"}
                for t in EGRESS_TARGETS]
    return [http_probe(t) for t in EGRESS_TARGETS]


# --------------------------------------------------------------------------------------
# vendor probes (credentialed, read-only, opt-in)
# --------------------------------------------------------------------------------------


def probe_fluid_topics(base=None):
    """Fluid Topics read API. docs.fluidtopics.com is a live public instance, so this
    probe works with no credentials and no procurement."""
    base = (base or "https://docs.fluidtopics.com").rstrip("/")
    url = "%s/api/khub/maps?lang=en" % base
    req = urllib.request.Request(url)
    req.add_header("User-Agent", USER_AGENT)
    req.add_header("Ft-Calling-App", "dac-probe")   # mandatory header
    out = {"vendor": "fluid-topics", "base": base, "url": url}
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            out.update(status=resp.status, reachable=True, bytes=len(resp.read(4096)))
        out["notes"] = ["Publishing needs only CONTENT_PUBLISHER; KHUB_ADMIN is required only to "
                        "CREATE a source. Ask for the smaller permission.",
                        "A permission failure returns 404, not 403 - do not misdiagnose it as a "
                        "wrong URL."]
    except urllib.error.HTTPError as exc:
        out.update(status=exc.code, reachable=False)
        if exc.code == 404:
            out["detail"] = ("404 here often means the API key is not in the source's allowedApiKeys "
                             "list, not that the URL is wrong.")
        elif exc.code == 401:
            out["detail"] = "Authentication required. Supply a Bearer API key."
    except Exception as exc:  # noqa: BLE001
        out.update(reachable=False, detail=str(exc))
    return out


def probe_oxygen_scripting():
    """Oxygen Scripting is the licence gate for any headless Oxygen automation. The
    documented mechanism is scriptinglicensekey.txt in the application root."""
    sysname = platform.system()
    roots = []
    if sysname == "Darwin":
        for parent in ("/Applications", os.path.expanduser("~/Applications")):
            if os.path.isdir(parent):
                roots += [os.path.join(parent, e) for e in os.listdir(parent)
                          if e.startswith("Oxygen XML")]
    elif sysname == "Windows":
        for base in (os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")):
            if base and os.path.isdir(base):
                roots += [os.path.join(base, e) for e in os.listdir(base)
                          if e.startswith("Oxygen XML")]
    else:
        if os.path.isdir("/opt"):
            roots += [os.path.join("/opt", e) for e in os.listdir("/opt")
                      if e.lower().startswith("oxygen")]

    out = {"vendor": "oxygen", "installs": roots, "scripting_licensed": False,
           "publishing_engine_licensed": False, "chemistry_licensed": False,
           "bundled_dita_ot": None}
    for root in roots:
        for cand in (os.path.join(root, "scriptinglicensekey.txt"),
                     os.path.join(root, "Contents", "app", "scriptinglicensekey.txt")):
            if os.path.isfile(cand):
                out["scripting_licensed"] = True
                out["scripting_key_path"] = cand
        for dh in (os.path.join(root, "frameworks", "dita", "DITA-OT"),
                   os.path.join(root, "Contents", "app", "frameworks", "dita", "DITA-OT")):
            if os.path.isdir(dh):
                out["dita_ot_dir"] = dh
                if os.path.isfile(os.path.join(dh, "licensekey.txt")):
                    out["publishing_engine_licensed"] = True
                chem = os.path.join(dh, "plugins", "com.oxygenxml.pdf.css", "lib",
                                    "oxygen-pdf-chemistry", "licensekey.txt")
                if os.path.isfile(chem):
                    out["chemistry_licensed"] = True
    if roots and not out["scripting_licensed"]:
        out["impact"] = ("No Oxygen Scripting licence, so there is no headless Oxygen and no "
                         "'Validate and Check For Completeness' in CI.")
        out["degrade"] = ("Use DITA-OT validate plus xmllint with an XML catalog, and Schematron "
                          "via a free CLI. Narrower rule coverage, no licence cost.")
        out["blocker_hint"] = "BLK-oxygen-scripting"
    out["notes"] = ["Publishing Engine, WebHelp and PDF Chemistry are SEPARATE purchases from "
                    "Scripting, each with its own licence key in its own location. No extra key is "
                    "needed when running inside a started Oxygen Editor - only from the CLI."]
    return out


def probe_vendors(enabled):
    probes = []
    if "fluid-topics" in enabled:
        probes.append(probe_fluid_topics(os.environ.get("FT_BASE_URL")))
    if "oxygen" in enabled:
        probes.append(probe_oxygen_scripting())
    return probes


# --------------------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------------------


def build_capabilities(runtime, egress):
    """Reduce probe results to the booleans the recipe graph actually branches on."""
    by = {r["name"]: r for r in runtime}
    eg = {e["id"]: e for e in egress}

    # "Not probed" is not the same as "blocked". When egress probing is skipped, assume
    # reachable rather than manufacturing blockers for things nobody has tested. Recording a
    # blocker the writer cannot act on - because it is an artefact of how DAC was invoked -
    # is worse than recording nothing.
    def reachable(target_id):
        e = eg.get(target_id, {})
        if e.get("verdict") == "skipped" or e.get("reachable") is None:
            return True
        return bool(e.get("reachable"))

    java_ok = by.get("java", {}).get("status") in ("ok", "ahead-of-tested")
    dita_ok = by.get("dita-ot", {}).get("present", False)
    docker_ok = by.get("docker", {}).get("status") == "ok"
    node_ok = by.get("node", {}).get("present", False)

    caps = {
        "can_build_native": bool(java_ok and dita_ok),
        "can_build_container": bool(docker_ok and reachable("ghcr")),
        # Downloadability and runnability are separate facts. Conflating them produces the
        # unhelpful message "you cannot install DITA-OT" when the real problem is Java.
        "can_download_dita_ot": reachable("github-releases"),
        "can_install_dita_ot": bool(java_ok and reachable("github-releases")),
        "can_lint_prose_dita": bool(dita_ok and java_ok and by.get("vale", {}).get("present")),
        "can_normalise_xml": bool(node_ok and reachable("npm-registry")),
        "can_use_gradle_path": bool(java_ok and reachable("maven-central")),
        "can_install_plugins_by_id": reachable("dita-ot-registry"),
        "has_vcs_client": bool(by.get("git", {}).get("present")),
        "can_validate_rng": bool(by.get("jing", {}).get("present")),
        "can_validate_dtd": bool(by.get("xmllint", {}).get("present")),
    }

    caps["has_any_build_path"] = caps["can_build_native"] or caps["can_build_container"] \
        or caps["can_install_dita_ot"]

    blockers = []
    if not caps["has_any_build_path"]:
        # Name the actual missing link rather than the symptom.
        java_missing = not java_ok
        docker_dead = by.get("docker", {}).get("present") and not docker_ok
        why = []
        if java_missing:
            why.append("no usable Java 17+ on PATH")
        if docker_dead:
            why.append("the Docker client is installed but its daemon is not running")
        elif not by.get("docker", {}).get("present"):
            why.append("Docker is not installed")
        if caps["can_download_dita_ot"]:
            why.append("DITA-OT itself IS downloadable, so this is a runtime problem, not a "
                       "network one")
        blockers.append({
            "id": "BLK-no-build-path",
            "severity": "critical",
            "what": "Nothing on this machine can build DITA output yet.",
            "why": "; ".join(why) or "no runtime and no container available",
            "fix": "Pick one. Native: install Temurin 17 (brew install --cask temurin@17) then "
                   "DITA-OT %s - do NOT use a bare 'brew install dita-ot', which pulls a much "
                   "newer JDK than the toolkit is tested against. Container: start the Docker "
                   "daemon and use ghcr.io/dita-ot/dita-ot:%s."
                   % (DITA_OT_CURRENT, DITA_OT_CURRENT),
            "lane": "green",
        })
    elif not caps["can_build_native"] and caps["can_build_container"]:
        blockers.append({
            "id": "BLK-container-only",
            "severity": "info",
            "what": "Builds will run in a container rather than natively.",
            "why": "No usable local Java with DITA-OT, but Docker and ghcr.io are available.",
            "fix": "Nothing required. Install Temurin 17 later if you want faster local builds "
                   "and Vale prose linting of .dita files, which needs dita on PATH.",
        })
    if not caps["can_lint_prose_dita"]:
        blockers.append({
            "id": "BLK-no-prose-lint",
            "severity": "low",
            "what": "Vale cannot lint .dita files.",
            "why": "Vale drives the dita command internally, so it needs DITA-OT on PATH and Java.",
            "fix": "Install Temurin 17 and DITA-OT, or run prose linting only in CI where those "
                   "are available.",
        })
    if not caps["can_use_gradle_path"] and eg.get("maven-central", {}).get("reachable") is False:
        blockers.append({
            "id": "BLK-maven-blocked",
            "severity": "medium",
            "what": "Maven Central is not reachable.",
            "why": eg["maven-central"].get("detail",
                                           "Blocked or intercepted by network policy."),
            "fix": "Point Gradle at your internal artifact proxy, or use the plain DITA-OT CLI "
                   "path instead of a Gradle wrapper. DAC will prefer the CLI path.",
        })
    if not caps["can_normalise_xml"]:
        blockers.append({
            "id": "BLK-no-xml-formatter",
            "severity": "medium",
            "what": "@prettier/plugin-xml cannot be installed.",
            "why": "Node or the npm registry is unavailable.",
            "fix": "Install Node 20+ and allow registry.npmjs.org. Without deterministic XML "
                   "formatting, PR diffs of DITA source stay hard to review - which is the single "
                   "most common objection to DITA in a docs-as-code workflow.",
        })
    return caps, blockers


def run(root, skip_egress=False, vendors=()):
    runtime = probe_runtime()
    egress = probe_egress(skip=skip_egress)
    vendor = probe_vendors(set(vendors))
    caps, blockers = build_capabilities(runtime, egress)
    return {
        "dac_version": DAC_VERSION,
        "stage": "probe",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": os.path.abspath(root),
        "reference_versions": {"dita_ot_current": DITA_OT_CURRENT, "java_min": JAVA_MIN,
                               "java_tested_max": JAVA_TESTED_MAX,
                               "vale_dita_ignores_floor": vtuple_str(VALE_DITA_IGNORES_FLOOR)},
        "runtime": runtime,
        "egress": egress,
        "vendor": vendor,
        "capabilities": caps,
        "blockers": blockers,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="DAC capability prober")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--skip-egress", action="store_true",
                    help="do not make outbound network requests")
    ap.add_argument("--vendors", default="",
                    help="comma-separated vendor probes to run (fluid-topics,oxygen)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    vendors = [v.strip() for v in args.vendors.split(",") if v.strip()]
    result = run(args.root, skip_egress=args.skip_egress, vendors=vendors)
    payload = json.dumps(result, indent=2)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        if not args.quiet:
            print("probe: wrote %s" % args.out, file=sys.stderr)
            for r in result["runtime"]:
                mark = "ok " if r["present"] else "MISS"
                print("  %s %-10s %s" % (mark, r["name"], r.get("version") or
                                         r.get("detail", "")), file=sys.stderr)
            for e in result["egress"]:
                print("  %-4s %-18s %s" % ("ok" if e.get("reachable") else "NO",
                                           e["id"], e["verdict"]), file=sys.stderr)
            for k, v in result["capabilities"].items():
                print("  cap  %-26s %s" % (k, v), file=sys.stderr)
            for b in result["blockers"]:
                print("  !    %-10s %s" % (b["severity"], b["id"]), file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
