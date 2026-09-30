#!/usr/bin/env python3
"""DAC connect - point DAC at wherever the content actually lives.

The writer pastes one thing: a repository URL, the address they log into to write, a
network share path, or a local folder. This works out what it is and then either fetches
it or explains exactly how to get the content flowing.

    connect.py --source https://github.com/acme/docs.git --dest ./docs --clone
    connect.py --source https://acme.heretto.com
    connect.py --source "/Volumes/Shared/Documentation"
    connect.py --source https://docs.acme.com

Why this exists: the most common first-run outcome is a writer with an empty folder,
because their content lives in a CCMS and there is genuinely nothing on their laptop.
Telling them "no content found" is useless. Asking for a link and acting on it is not.

Only https and ssh Git remotes are cloned. Nothing else is fetched automatically, because
everything else needs either a credential or a human decision.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

DAC_VERSION = "0.1.0"

# ----------------------------------------------------------------------------------------
# Recognisers. Ordered most-specific first; the first match wins.
# ----------------------------------------------------------------------------------------

GIT_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "dev.azure.com",
             "visualstudio.com", "gitea.", "codeberg.org", "sourcehut.org", "git.")

# Hostname and path patterns that identify an authoring or delivery system. Each maps to a
# pack id in packs/, so the guidance below stays consistent with the vendor research.
VENDOR_PATTERNS = [
    (r"\.heretto\.com", "heretto"),
    (r"\.easydita\.com", "heretto"),
    (r"\.paligoapp\.com", "paligo"),
    # Lowercase: these are matched against a lowercased URL.
    (r"/ishws/", "tridion-docs"),
    (r"\.fluidtopics\.(net|com)", "fluid-topics"),
    (r"\.zoominsoftware\.io", "zoomin"),
    (r"ixiasoft|ixia-ccms|/ixiasoft-ccms", "ixia-ccms"),
    (r"experience\.adobe\.com|\.adobeaemcloud\.com|/bin/guides/", "aem-guides"),
    (r"\.author-it\.com", "author-it"),
    (r"\.madcapcentral\.com|madcapsoftware\.com", "madcap-flare"),
    (r"\.componize\.|/alfresco/", "componize"),
    (r"bluestream\.com|xdocs", "bluestream-xdocs"),
]

# Platforms that host *published output* rather than DITA source. Being pointed at one of
# these is a common and understandable mistake, and worth naming clearly.
PUBLISHED_OUTPUT_HOSTS = [
    (r"readme\.io|readme\.com", "ReadMe"),
    (r"gitbook\.(io|com)", "GitBook"),
    (r"document360\.io", "Document360"),
    (r"readthedocs\.(io|org)", "Read the Docs"),
    (r"\.netlify\.app|\.vercel\.app|\.github\.io|\.pages\.dev", "a static site host"),
]

SHARE_PREFIXES = ("smb://", "afp://", "//", "\\\\", "/Volumes/", "/mnt/", "/media/",
                  "Z:", "Y:", "X:")


def classify(source):
    """Work out what the writer just handed us."""
    s = (source or "").strip()
    low = s.lower()

    if not s:
        return {"kind": "empty"}

    # A local path that exists is the simplest possible answer.
    if os.path.isdir(os.path.expanduser(s)):
        p = os.path.abspath(os.path.expanduser(s))
        on_share = any(p.startswith(x) for x in ("/Volumes/", "/mnt/", "/media/"))
        return {"kind": "network_share" if on_share else "local_dir", "path": p}

    # Git remotes. SSH shorthand (git@host:org/repo) is not a URL, so check it explicitly.
    if re.match(r"^(git|ssh)@[^:]+:.+", s) or low.startswith(("ssh://", "git://")):
        return {"kind": "git", "url": s, "transport": "ssh"}
    if low.endswith(".git"):
        return {"kind": "git", "url": s, "transport": "https"}
    if low.startswith(("http://", "https://")):
        host = re.sub(r"^https?://", "", low).split("/")[0]

        # A vendor system takes precedence over a generic Git host guess.
        for pat, vendor in VENDOR_PATTERNS:
            if re.search(pat, low):
                return {"kind": "vendor", "vendor": vendor, "url": s, "host": host}
        for pat, name in PUBLISHED_OUTPUT_HOSTS:
            if re.search(pat, low):
                return {"kind": "published_output", "platform": name, "url": s, "host": host}
        if any(h in host for h in GIT_HOSTS):
            return {"kind": "git", "url": s, "transport": "https"}
        # Heuristic, checked after the known hosts: a writer pasting their *public*
        # documentation address is a very common and understandable mistake, and these
        # hostname prefixes are a strong signal of published output rather than source.
        if re.match(r"^(docs|doc|help|documentation|support|learn|developer|devdocs)\.", host):
            return {"kind": "published_output", "platform": "your own documentation site",
                    "url": s, "host": host, "heuristic": True}
        return {"kind": "unknown_url", "url": s, "host": host}

    if any(low.startswith(x.lower()) for x in SHARE_PREFIXES):
        return {"kind": "network_share", "path": s}

    # A path-looking string that does not exist.
    if s.startswith(("/", "~", "./", "../")) or re.match(r"^[A-Za-z]:\\", s):
        return {"kind": "missing_path", "path": s}

    return {"kind": "unrecognised", "value": s}


# ----------------------------------------------------------------------------------------
# Git
# ----------------------------------------------------------------------------------------


def normalise_git_url(url):
    """Strip things people paste by accident: a trailing slash, /tree/main, .git twice."""
    u = url.strip().rstrip("/")
    u = re.sub(r"/(tree|blob)/[^/]+/?.*$", "", u)
    u = re.sub(r"\.git\.git$", ".git", u)
    return u


def clone(url, dest, shallow=True, quiet=False):
    """Clone a repository. Refuses to write into a non-empty directory."""
    if not shutil.which("git"):
        return {"ok": False, "reason": "git is not installed",
                "fix": "Install Git, then run this again. On macOS: brew install git"}
    dest = os.path.abspath(os.path.expanduser(dest))
    if os.path.isdir(dest) and os.listdir(dest):
        return {"ok": False, "reason": "destination is not empty: %s" % dest,
                "fix": "Choose an empty folder, or if the repository is already there just "
                       "run the audit against it directly."}
    cmd = ["git", "clone"]
    if shallow:
        # Shallow by default: writers rarely need the full history to set up a pipeline,
        # and a large DITA estate can be hundreds of megabytes of it.
        cmd += ["--depth", "1"]
    cmd += [url, dest]
    if not quiet:
        print("  running: %s" % " ".join(cmd), file=sys.stderr)
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              timeout=1800)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": "clone timed out after 30 minutes"}
    except OSError as exc:
        return {"ok": False, "reason": str(exc)}
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        fix = ("Check the URL is right and that you have access to it. If it is a private "
               "repository you may need to sign in first - on GitHub, `gh auth login` is "
               "the easiest way.")
        if "authentication" in out.lower() or "permission denied" in out.lower():
            fix = ("This repository needs authentication. Run `gh auth login` for GitHub, or "
                   "ask whoever owns the repository to give your account read access.")
        elif "not found" in out.lower():
            fix = ("The repository was not found. Either the URL has a typo, or it is private "
                   "and your account cannot see it.")
        return {"ok": False, "reason": out[-500:], "fix": fix}
    return {"ok": True, "dest": dest, "shallow": shallow}


# ----------------------------------------------------------------------------------------
# Vendor guidance. Reflects the research in packs/ - notably that NO CCMS syncs DITA
# source to Git, so every one of these is a bridge DAC builds rather than switches on.
# ----------------------------------------------------------------------------------------

VENDOR_GUIDANCE = {
    "heretto": {
        "name": "Heretto CCMS",
        "archetype": "B",
        "what_dac_does": "Sets up a scheduled one-way export that copies your DITA source into "
                         "this folder, then builds validation and publishing around it.",
        "need_from_you": [
            "Your Heretto organisation id - the first part of your Heretto web address",
            "An API token, generated in Heretto under your user settings",
        ],
        "ask_someone": "Your Heretto **Customer Success Manager** - NOT an administrator. The "
                       "API that reads content is v1 and its documentation is only available on "
                       "request, and webhooks may need enabling for your organisation. An admin "
                       "cannot help with this and will just forward the request.",
        "honest_note": "Heretto's DITA-OT Cloud supports toolkit versions 2.5.4 to 3.7.4, while "
                       "current DITA-OT is 4.4.1. Output built here will not be byte-identical "
                       "to output built in Heretto. That difference is worth knowing before you "
                       "compare them.",
    },
    "ixia-ccms": {
        "name": "MadCap IXIA CCMS",
        "archetype": "B",
        "what_dac_does": "Runs the CCMS 'Export' scenario on a schedule and commits the raw "
                         "DITA it returns.",
        "need_from_you": [
            "Your CCMS web address",
            "A username and password with permission to run the Export scenario",
        ],
        "ask_someone": "A **System Administrator** - the Export scenario is admin-only in the "
                       "default configuration.",
        "honest_note": "Two things MadCap says plainly. Re-importing edited content 'is an "
                       "overwrite, not a merge', so this sync is one-way and will stay one-way. "
                       "And only unreleased or locked content lives on disk - released content "
                       "sits on the server, so the first export may show less than you expect.",
    },
    "tridion-docs": {
        "name": "RWS Tridion Docs",
        "archetype": "B",
        "what_dac_does": "Uses ISHRemote, the RWS-maintained PowerShell module, to retrieve "
                         "publication content on a schedule.",
        "need_from_you": [
            "Your ISHWS web address (it contains /ISHWS/)",
            "OAuth client credentials - a client id and secret",
        ],
        "ask_someone": "Whoever administers Tridion Docs, for a **service account** with client "
                       "credentials. A username and password will not work on version 15.x - it "
                       "fails with an invalid_client error.",
        "honest_note": "PowerShell and the ISHRemote module are required. Pin ISHRemote 8.2 or "
                       "later; 8.1 fails to load on current PowerShell.",
    },
    "aem-guides": {
        "name": "Adobe Experience Manager Guides",
        "archetype": "B",
        "what_dac_does": "Pulls DITA assets through the AEM Assets API on a schedule.",
        "need_from_you": [
            "Your AEM author instance address",
            "Adobe IMS Server-to-Server credentials - a client id and secret",
        ],
        "ask_someone": "Whoever owns your **Adobe Developer Console** - usually IT or a platform "
                       "team, not the documentation team. These credentials cannot be created "
                       "from inside AEM.",
        "honest_note": "Two things change the design here. AEM Guides defaults to a CSS-based "
                       "Native PDF engine rather than DITA-OT, so a local PDF will never match "
                       "the reference output. And if you are on a UUID build, references are "
                       "UUID-based, which means an ordinary link checker passes clean on "
                       "genuinely broken links.",
    },
    "paligo": {
        "name": "Paligo",
        "archetype": "B",
        "what_dac_does": "Nothing yet, and this one needs a decision from you first.",
        "need_from_you": [
            "An API key created under an admin account",
        ],
        "ask_someone": "A **Paligo administrator**. Paligo's documentation states the API user "
                       "must be an admin user, with no exceptions, and licence permissions carry "
                       "into the API - so a non-admin key cannot be made to work.",
        "honest_note": "Paligo content is **DocBook 5.1, not DITA**. Paligo says so itself. You "
                       "can export it, but converting DocBook to DITA is genuine XSLT work that "
                       "DAC will scope and will not perform. Also avoid the DocBook publish "
                       "output: it strips variables and text fragments. The API returns "
                       "higher-fidelity source.",
    },
    "fluid-topics": {
        "name": "Fluid Topics",
        "archetype": "D",
        "what_dac_does": "Wires Fluid Topics as the publishing destination. This is a delivery "
                         "platform, so your source has to come from somewhere else as well.",
        "need_from_you": [
            "Your Fluid Topics tenant address",
            "An API key",
        ],
        "ask_someone": "A tenant admin - but ask for the **CONTENT_PUBLISHER** role only. "
                       "Publishing does not need KHUB_ADMIN, and asking for more privilege than "
                       "the job needs is how these requests get refused.",
        "honest_note": "Where is your DITA source? Fluid Topics receives published content; it "
                       "is not where you author. Point DAC at the source system too.",
    },
    "madcap-flare": {
        "name": "MadCap Flare",
        "archetype": "C",
        "what_dac_does": "Works with your Flare project as it is. Flare already has first-class "
                         "Git support, so you may be further along than you think.",
        "need_from_you": [
            "The path to your local Flare project folder, the one containing the .flprj file",
        ],
        "ask_someone": "Nobody, to start. Later, whoever owns MadCap licensing - unattended CI "
                       "builds need an enterprise floating licence.",
        "honest_note": "Flare source is XHTML, not DITA, so you get version control, CI, linting "
                       "and automated publishing, but not semantic diffs or DITA-style component "
                       "reuse. That limit is real and worth knowing up front.",
    },
    "zoomin": {
        "name": "Zoomin",
        "archetype": "D",
        "what_dac_does": "Deliberately nothing. DAC will not wire a publishing step to Zoomin.",
        "need_from_you": [],
        "ask_someone": "Whoever owns the Zoomin contract, to confirm your end date.",
        "honest_note": "Salesforce ended renewals on 1 September 2025 for the Zoomin "
                       "documentation portal, In-Product Help, the API and Headless products. "
                       "Existing contracts are being honoured, in some cases into 2026. Plan a "
                       "replacement rather than an integration. The good news is that your DITA "
                       "source and build are independent of the delivery platform, so switching "
                       "later is configuration, not migration.",
    },
    "author-it": {
        "name": "Author-it",
        "archetype": "C",
        "what_dac_does": "Limited. Author-it's automation surface is outbound only.",
        "need_from_you": ["Access to the Author-it library"],
        "ask_someone": "An Author-it administrator, to run an XML export or configure the "
                       "after-publish HTTP Post action.",
        "honest_note": "Author-it stores content in a proprietary relational database, not DITA "
                       "and not XML-native. Export is a manual UI operation and there is no "
                       "documented API for reading content programmatically. AION, its JSON "
                       "output, is free in every subscription and is the most automatable route.",
    },
    "componize": {
        "name": "Componize",
        "archetype": "B",
        "what_dac_does": "Exports through CMIS, the standardised Alfresco protocol.",
        "need_from_you": ["Your Alfresco address", "Credentials with read access"],
        "ask_someone": "Whoever administers Alfresco.",
        "honest_note": "Componize advertises REST and Java APIs but publishes no endpoint "
                       "reference, so DAC treats them as unverified and uses CMIS instead. The "
                       "embedded DITA-OT version is not published either and has to be probed.",
    },
    "bluestream-xdocs": {
        "name": "Bluestream XDocs",
        "archetype": "B",
        "what_dac_does": "Needs investigation before anything can be automated.",
        "need_from_you": ["Whatever API documentation Bluestream has given you"],
        "ask_someone": "Your Bluestream contact, for API documentation.",
        "honest_note": "XDocs' APIs are described in marketing material but no public endpoint "
                       "reference, base URL or auth scheme exists. Be careful searching for it: "
                       "docs.xdocm.com documents an unrelated mortgage document product, and "
                       "following it will produce a confidently wrong integration.",
    },
}


def vendor_guidance(vendor):
    return VENDOR_GUIDANCE.get(vendor, {
        "name": vendor,
        "archetype": "?",
        "what_dac_does": "Researches the system before attempting anything.",
        "need_from_you": [],
        "ask_someone": "Whoever administers it.",
        "honest_note": "DAC does not have a verified capability pack for this system. Run "
                       "`dac vendors research %s` first. Nothing will be automated against it "
                       "until its capabilities are confirmed rather than assumed." % vendor,
    })


# ----------------------------------------------------------------------------------------
# Human-readable outcome
# ----------------------------------------------------------------------------------------


def render(result):
    L = []
    w = L.append
    c = result["classification"]
    kind = c["kind"]

    if kind == "git":
        w("This is a Git repository.")
        w("")
        cl = result.get("clone")
        if cl and cl.get("ok"):
            w("Cloned to: %s" % cl["dest"])
            if cl.get("shallow"):
                w("")
                w("Only the latest version was downloaded, which is all a pipeline needs. If you "
                  "later want the full history: git fetch --unshallow")
            w("")
            w("Next: run the audit against that folder.")
            w("    dac audit --root %s" % cl["dest"])
        elif cl:
            w("The clone did not work.")
            w("")
            w("  Reason: %s" % cl.get("reason", "unknown"))
            if cl.get("fix"):
                w("  Fix:    %s" % cl["fix"])
        else:
            w("To bring it down, run:")
            w("")
            w("    git clone --depth 1 %s %s" % (result["normalised_url"],
                                                 result.get("dest") or "docs"))
            w("")
            w("Then run the audit inside that folder. Add --clone to have DAC do this for you.")

    elif kind == "vendor":
        g = result["guidance"]
        w("This is **%s** (archetype %s)." % (g["name"], g["archetype"]))
        w("")
        w("What DAC will do: %s" % g["what_dac_does"])
        w("")
        if g["need_from_you"]:
            w("What it needs from you:")
            for n in g["need_from_you"]:
                w("  - %s" % n)
            w("")
        w("Who to ask: %s" % g["ask_someone"])
        w("")
        w("Worth knowing: %s" % g["honest_note"])
        w("")
        if g["archetype"] == "B":
            w("Important, so it is not a surprise later: **no CCMS on the market synchronises "
              "DITA source to Git.** This export bridge is something DAC builds for you, not a "
              "feature it switches on. It runs one way, out of the CCMS only - nothing is ever "
              "written back. You keep authoring exactly where you do today.")
            w("")
        w("Next: run the audit in an empty folder and supply those details when asked.")

    elif kind == "published_output":
        w("This looks like a **published documentation site** hosted on %s, rather than the "
          "source your team writes in." % c["platform"])
        w("")
        w("DAC needs the source - the `.dita` and `.ditamap` files, or the system you log into "
          "to edit pages. The published site is what comes *out* of the pipeline.")
        w("")
        w("If you are not sure where the source is, the question that usually settles it is: "
          "what do you open in the morning to change a page?")
        w("")
        if c.get("heuristic"):
            w("This is a guess based on the address starting with `%s`. If %s really is where "
              "your source lives, re-run with --kind vendor or --kind git to override."
              % (c["host"].split(".")[0], c["host"]))
        else:
            w("Note that %s does not accept DITA as an input format, so if that is your "
              "publishing destination the pipeline will need a conversion step from DITA-OT "
              "output." % c["platform"])

    elif kind == "local_dir":
        w("This is a folder on this computer: %s" % c["path"])
        w("")
        w("Nothing to fetch. Run the audit against it directly:")
        w("")
        w("    dac audit --root \"%s\"" % c["path"])

    elif kind == "network_share":
        w("This looks like a network share or an external volume.")
        w("")
        w("**Copy it to your own computer first, then work on the copy.** Git is slow and "
          "unreliable on a network share, and a half-finished operation on one can be genuinely "
          "hard to recover from.")
        w("")
        w("    cp -R \"%s\" ~/docs-local" % c.get("path", "<the share>"))
        w("    dac audit --root ~/docs-local")
        w("")
        w("DAC deliberately does not copy it for you. On a large documentation estate this can "
          "take a long time and it is worth watching.")

    elif kind == "missing_path":
        w("That looks like a folder path, but there is nothing at %s." % c["path"])
        w("")
        w("Check for a typo. If you are not sure of the path, your editor's list of recently "
          "opened projects is the quickest way to find it.")

    elif kind == "unknown_url":
        w("DAC does not recognise %s." % c["host"])
        w("")
        w("If it is a Git repository, add `.git` to the end of the URL, or pass --kind git to "
          "force it.")
        w("")
        w("If it is a content management system DAC has not seen before, run:")
        w("")
        w("    dac vendors research %s" % c["host"])
        w("")
        w("That researches its documentation and builds a capability pack. Nothing will be "
          "automated against it until its capabilities are verified rather than assumed.")

    elif kind == "empty":
        w("Nothing was supplied. Pass --source with a repository URL, the address you log into "
          "to write, or a folder path.")

    else:
        w("DAC could not tell what '%s' is." % c.get("value", ""))
        w("")
        w("It accepts any of these:")
        w("  - a Git repository URL, for example https://github.com/acme/docs.git")
        w("  - the web address you log into to write, for example https://acme.heretto.com")
        w("  - a folder path on this computer")
        w("  - a network share path")

    return "\n".join(L)


# ----------------------------------------------------------------------------------------


def run(source, dest=None, do_clone=False, shallow=True, force_kind=None, quiet=False):
    c = classify(source)
    if force_kind:
        c = {"kind": force_kind, "url": source}

    result = {
        "dac_version": DAC_VERSION,
        "stage": "connect",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "classification": c,
    }

    if c["kind"] == "git":
        result["normalised_url"] = normalise_git_url(c["url"])
        default_dest = dest or re.sub(r"\.git$", "", result["normalised_url"].rstrip("/")
                                      ).split("/")[-1] or "docs"
        result["dest"] = default_dest
        if do_clone:
            result["clone"] = clone(result["normalised_url"], default_dest,
                                    shallow=shallow, quiet=quiet)
    elif c["kind"] == "vendor":
        result["guidance"] = vendor_guidance(c["vendor"])
        result["pack"] = c["vendor"]

    result["message"] = render(result)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Point DAC at wherever your documentation actually lives")
    ap.add_argument("--source", required=True,
                    help="a Git URL, the address you log into to write, or a folder path")
    ap.add_argument("--dest", help="where to clone to (Git sources only)")
    ap.add_argument("--clone", action="store_true",
                    help="actually clone, rather than only printing the command")
    ap.add_argument("--full-history", action="store_true",
                    help="clone the full history instead of only the latest version")
    ap.add_argument("--kind", choices=("git", "vendor", "local_dir"),
                    help="force the classification when detection guesses wrong")
    ap.add_argument("--out", help="also write JSON here")
    ap.add_argument("--json", action="store_true", help="print JSON instead of prose")
    args = ap.parse_args(argv)

    result = run(args.source, dest=args.dest, do_clone=args.clone,
                 shallow=not args.full_history, force_kind=args.kind, quiet=args.json)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(result, indent=2) + "\n")

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["message"])

    cl = result.get("clone")
    if cl and not cl.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
