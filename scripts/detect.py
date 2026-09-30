#!/usr/bin/env python3
"""DAC detector - credential-free fingerprinting of a structured-content ecosystem.

Walks a target tree once, indexes it, then evaluates vendor signals against the index.
Emits JSON on stdout or to --out. Reads nothing outside --root except environment
variables and well-known install paths. Never writes to the target tree.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import platform
import re
import shutil
import sys
from datetime import datetime, timezone

DAC_VERSION = "0.1.0"

# Directories never walked into. Their presence is still recorded, because for some
# vendors (Flare's Output/, Analyzer/, FileSync/) existing in a repo is itself a finding.
PRUNE_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "__pycache__", ".gradle", ".idea",
    ".venv", "venv", "dist", "target", "out", "output", "temp", "tmp",
    "build", "Output", "Analyzer", "FileSync", "vendor", ".dac", ".terraform",
    ".pytest_cache", ".mypy_cache", "bower_components", ".next", ".nuxt",
}

MAX_FILES = 400_000
MAX_CONTENT_READS = 3_000
CONTENT_READ_BYTES = 131_072
SAMPLE_CAP = 6

DITA_SOURCE_EXTS = {".dita", ".ditamap", ".bookmap", ".ditaval", ".xml"}

# --------------------------------------------------------------------------------------
# Index
# --------------------------------------------------------------------------------------


class Index:
    """A single-pass, queryable picture of the tree."""

    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.ext_counts = {}
        self.basenames = {}      # lowercased basename -> [relpaths]
        self.dirnames = {}       # lowercased dirname   -> [relpaths]
        self.pruned_dirs = {}    # lowercased dirname   -> [relpaths]
        self.total_files = 0
        self.truncated = False
        self.errors = []
        self.skipped_self = []

    def _add(self, bucket, key, relpath):
        lst = bucket.setdefault(key, [])
        if len(lst) < SAMPLE_CAP:
            lst.append(relpath)

    def rel(self, path):
        try:
            return os.path.relpath(path, self.root)
        except ValueError:
            return path

    def _is_dac_itself(self, dirpath, filenames):
        """True if this directory is a DAC skill install.

        Without this, DAC detects every vendor it documents when pointed at its own
        source tree, because its reference files legitimately name all of them.
        """
        if "SKILL.md" not in filenames:
            return False
        return "name: dita-as-code" in read_head(os.path.join(dirpath, "SKILL.md"), 2048)

    def build(self):
        for dirpath, dirnames, filenames in os.walk(self.root, onerror=self._on_error):
            if self._is_dac_itself(dirpath, filenames):
                dirnames[:] = []
                self.skipped_self.append(self.rel(dirpath))
                continue
            keep = []
            for d in dirnames:
                rel = self.rel(os.path.join(dirpath, d))
                if d in PRUNE_DIRS:
                    self._add(self.pruned_dirs, d.lower(), rel)
                else:
                    keep.append(d)
                    self._add(self.dirnames, d.lower(), rel)
            dirnames[:] = keep

            for fn in filenames:
                if self.total_files >= MAX_FILES:
                    self.truncated = True
                    return self
                self.total_files += 1
                rel = self.rel(os.path.join(dirpath, fn))
                ext = os.path.splitext(fn)[1].lower()
                if ext:
                    self.ext_counts[ext] = self.ext_counts.get(ext, 0) + 1
                self._add(self.basenames, fn.lower(), rel)
        return self

    def _on_error(self, exc):
        self.errors.append(str(exc))

    # -- queries -----------------------------------------------------------------------

    def ext(self, *exts):
        return sum(self.ext_counts.get(e.lower(), 0) for e in exts)

    def ext_samples(self, *exts):
        wanted = {e.lower() for e in exts}
        out = []
        for name, paths in self.basenames.items():
            if os.path.splitext(name)[1] in wanted:
                out.extend(paths)
                if len(out) >= SAMPLE_CAP:
                    break
        return out[:SAMPLE_CAP]

    def basename(self, name):
        return self.basenames.get(name.lower(), [])

    def basename_re(self, pattern):
        rx = re.compile(pattern, re.IGNORECASE)
        out = []
        for name, paths in self.basenames.items():
            if rx.match(name):
                out.extend(paths)
                if len(out) >= SAMPLE_CAP:
                    break
        return out[:SAMPLE_CAP]

    def dirname(self, name):
        return self.dirnames.get(name.lower(), [])

    def pruned(self, name):
        return self.pruned_dirs.get(name.lower(), [])

    def iter_files_with_ext(self, exts, cap=MAX_CONTENT_READS):
        wanted = {e.lower() for e in exts}
        seen = 0
        for dirpath, dirnames, filenames in os.walk(self.root, onerror=self._on_error):
            if self._is_dac_itself(dirpath, filenames):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
            for fn in filenames:
                if os.path.splitext(fn)[1].lower() in wanted:
                    if seen >= cap:
                        return
                    seen += 1
                    yield os.path.join(dirpath, fn)


def read_head(path, nbytes=CONTENT_READ_BYTES):
    try:
        with open(path, "rb") as fh:
            return fh.read(nbytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------------------
# Evidence and findings
# --------------------------------------------------------------------------------------


def ev(kind, detail, samples=None, weight=1):
    item = {"kind": kind, "detail": detail, "weight": weight}
    if samples:
        item["samples"] = list(samples)[:SAMPLE_CAP]
    return item


def confidence_for(score):
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    if score >= 1:
        return "low"
    return "none"


class Finding:
    # kind="content"   this system holds or is the content, so it sets the archetype
    # kind="toolchain" a tool is installed. Says NOTHING about where content lives, and
    #                  must never contribute an archetype. Conflating the two made DAC
    #                  claim "your content is already portable DITA sitting in files"
    #                  when pointed at a completely empty folder.
    def __init__(self, vendor, display_name, archetype, pack=None, kind="content"):
        self.vendor = vendor
        self.display_name = display_name
        self.archetype = archetype
        self.pack = pack or vendor
        self.kind = kind
        self.evidence = []
        self.notes = []

    def add(self, item):
        if item:
            self.evidence.append(item)
        return self

    def note(self, text):
        self.notes.append(text)
        return self

    @property
    def score(self):
        return sum(e.get("weight", 1) for e in self.evidence)

    def to_dict(self):
        return {
            "vendor": self.vendor,
            "display_name": self.display_name,
            "archetype": self.archetype,
            "pack": self.pack,
            "kind": self.kind,
            "score": self.score,
            "confidence": confidence_for(self.score),
            "evidence": self.evidence,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------------------
# Install-path probes (platform aware, read-only)
# --------------------------------------------------------------------------------------


def existing(paths):
    return [p for p in paths if p and os.path.exists(p)]


def glob_dirs(parent, pattern):
    """List entries of `parent` matching a regex, without importing glob semantics."""
    if not parent or not os.path.isdir(parent):
        return []
    rx = re.compile(pattern, re.IGNORECASE)
    try:
        return [os.path.join(parent, e) for e in sorted(os.listdir(parent)) if rx.match(e)]
    except OSError:
        return []


def install_candidates():
    sysname = platform.system()
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    pdata = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    home = os.path.expanduser("~")

    c = {"oxygen": [], "arbortext": [], "xmetal": [], "framemaker": [], "flare": [], "ixia": []}

    if sysname == "Darwin":
        c["oxygen"] += glob_dirs("/Applications", r"Oxygen XML (Editor|Author|Developer).*\.app$")
        c["oxygen"] += glob_dirs(os.path.join(home, "Applications"),
                                 r"Oxygen XML (Editor|Author|Developer).*\.app$")
        c["framemaker"] += glob_dirs("/Applications", r"Adobe FrameMaker.*")
    elif sysname == "Windows":
        for base in (pf, pf86):
            c["oxygen"] += glob_dirs(base, r"Oxygen XML (Editor|Author|Developer).*")
            c["arbortext"] += glob_dirs(os.path.join(base, "PTC"), r"Arbortext.*")
            c["xmetal"] += glob_dirs(os.path.join(base, "XMetaL"), r".*")
            c["framemaker"] += glob_dirs(base, r"Adobe.*")
            c["flare"] += glob_dirs(base, r"MadCap.*")
        c["xmetal"] += existing([os.path.join(pdata, "SoftQuad", "XMetaL")])
        c["ixia"] += glob_dirs("C:\\", r"ixiasoft-ccms.*") + existing([r"C:\Ixiasoft\ccms"])
    else:
        c["oxygen"] += glob_dirs("/opt", r"oxygen.*") + glob_dirs(home, r"oxygen.*")
        c["ixia"] += existing(["/opt/ixiasoft/ccms"])

    return {k: existing(v) for k, v in c.items()}


def find_file_under(root, name, max_depth=4):
    """Shallow search for a file under an install root. Returns first hit or None."""
    if not root or not os.path.isdir(root):
        return None
    root = os.path.abspath(root)
    base_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - base_depth >= max_depth:
            dirnames[:] = []
        for fn in filenames:
            if fn.lower() == name.lower():
                return os.path.join(dirpath, fn)
    return None


def dita_ot_version_at(install_dir):
    """Read a DITA-OT version out of an installation directory."""
    for rel in ("config/env.sh", "config/configuration.properties", "bin/dita"):
        p = os.path.join(install_dir, rel)
        if os.path.isfile(p):
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", read_head(p, 8192))
            if m:
                return m.group(1)
    m = re.search(r"dita-ot[-_]?(\d+\.\d+(?:\.\d+)?)", os.path.basename(install_dir), re.I)
    return m.group(1) if m else None


# --------------------------------------------------------------------------------------
# Vendor detectors
# --------------------------------------------------------------------------------------


def detect_native_dita(idx, dita_stats):
    maps = idx.ext(".ditamap", ".bookmap")
    topics = idx.ext(".dita")
    if not maps and not topics:
        return None
    f = Finding("native-dita", "Native DITA on disk", ["A"], pack="dita-ot")
    if maps:
        f.add(ev("ext", "%d DITA map file(s)" % maps, idx.ext_samples(".ditamap", ".bookmap"), 4))
    if topics:
        f.add(ev("ext", "%d .dita topic file(s)" % topics, idx.ext_samples(".dita"), 4))
    if idx.ext(".ditaval"):
        f.add(ev("ext", "%d .ditaval filter file(s)" % idx.ext(".ditaval"),
                 idx.ext_samples(".ditaval"), 2))
    if dita_stats.get("conref_files"):
        f.add(ev("content", "%d file(s) use @conref/@conkeyref" % dita_stats["conref_files"],
                 dita_stats.get("conref_samples"), 2))
    if dita_stats.get("keyref_files"):
        f.add(ev("content", "%d file(s) use @keyref/@conkeyref" % dita_stats["keyref_files"],
                 dita_stats.get("keyref_samples"), 1))
    if dita_stats.get("subjectscheme_files"):
        f.add(ev("content", "%d subjectScheme map(s) - taxonomy-driven profiling in use"
                 % dita_stats["subjectscheme_files"], dita_stats.get("subjectscheme_samples"), 1))
    f.note("Content is already portable DITA. The authoring tool being GUI-only is irrelevant to "
           "the pipeline - DAC automates from the save onward.")
    return f


def detect_oxygen(idx, installs):
    # Archetype starts at A and is promoted to include E only if a Publishing Engine
    # licence is actually found. Oxygen *can* be a render service, but claiming it
    # without evidence overstates what this team has.
    f = Finding("oxygen", "Oxygen XML Editor / Author", ["A"])
    xpr = idx.ext(".xpr")
    if xpr:
        f.add(ev("ext", "%d Oxygen project file(s) (.xpr)" % xpr, idx.ext_samples(".xpr"), 4))
    if idx.dirname(".oxygen"):
        f.add(ev("dir", "project-local .oxygen/ framework directory", idx.dirname(".oxygen"), 3))
    for root in installs.get("oxygen", []):
        f.add(ev("install", "installation at %s" % root, weight=3))
        # Scripting licence: the documented mechanism is a file in the app root,
        # the parent of scripts/. Absence means no headless Oxygen.
        key = os.path.join(root, "scriptinglicensekey.txt")
        nested = find_file_under(root, "scriptinglicensekey.txt", max_depth=3)
        if os.path.isfile(key) or nested:
            f.add(ev("licence", "Oxygen Scripting licence key present", [key if
                     os.path.isfile(key) else nested], 2))
            f.note("Oxygen Scripting is licensed. Headless validation and "
                   "'Validate and Check For Completeness' are available.")
        else:
            f.note("No scriptinglicensekey.txt found. Oxygen Scripting is a separate commercial "
                   "purchase; without it there is no headless Oxygen. DAC will degrade to "
                   "DITA-OT validate plus xmllint.")
        dita_home = os.path.join(root, "frameworks", "dita", "DITA-OT")
        if os.path.isdir(dita_home):
            ver = dita_ot_version_at(dita_home)
            f.add(ev("bundled", "bundled DITA-OT%s at %s" % (" " + ver if ver else "", dita_home),
                     weight=2))
            if ver:
                f.note("Oxygen bundles DITA-OT %s. Pin CI to this version so local and CI output "
                       "match." % ver)
        for lic, what in ((os.path.join(dita_home, "licensekey.txt"), "Oxygen Publishing Engine"),
                          (os.path.join(dita_home, "plugins", "com.oxygenxml.pdf.css", "lib",
                                        "oxygen-pdf-chemistry", "licensekey.txt"),
                           "Oxygen PDF Chemistry")):
            if os.path.isfile(lic):
                f.add(ev("licence", "%s licence key present" % what, [lic], 1))
                if "E" not in f.archetype:
                    f.archetype = f.archetype + ["E"]
    if f.score and "E" not in f.archetype:
        f.note("No Publishing Engine or PDF Chemistry licence key was found, so this is a "
               "file-based authoring setup rather than a server-side render service. Publishing "
               "Engine, WebHelp and PDF Chemistry are separate purchases.")
    return f if f.score else None


def detect_content_fusion(idx):
    hits = idx.basename_re(r"content-fusion.*") + idx.basename("cf-project.xml")
    if not hits:
        return None
    f = Finding("oxygen-content-fusion", "Oxygen Content Fusion", ["A"])
    f.add(ev("file", "Content Fusion project artefacts", hits, 3))
    f.note("Content Fusion mirrors a Git repository with per-branch author workspaces and "
           "automatic review branches. For an Oxygen shop this is the shortest existing path to "
           "docs-as-code - archetype A, not a CCMS.")
    return f


def detect_arbortext(idx, installs):
    # As with Oxygen: A by default, promoted to E only on evidence of a Publishing Engine.
    f = Finding("arbortext", "PTC Arbortext Editor", ["A"])
    if idx.ext(".acl"):
        f.add(ev("ext", "%d Arbortext Command Language file(s) (.acl)" % idx.ext(".acl"),
                 idx.ext_samples(".acl"), 3))
    if idx.ext(".dcf"):
        f.add(ev("ext", "%d document configuration file(s) (.dcf)" % idx.ext(".dcf"),
                 idx.ext_samples(".dcf"), 2))
    if idx.ext(".style"):
        f.add(ev("ext", "%d Styler stylesheet(s) (.style)" % idx.ext(".style"),
                 idx.ext_samples(".style"), 2))
    for d in ("custom",):
        for rel in idx.dirname(d):
            if os.path.isdir(os.path.join(idx.root, rel, "init")):
                f.add(ev("dir", "Arbortext custom/init/ customization tree", [rel], 3))
    if idx.basename("e3config.xml"):
        f.add(ev("file", "Publishing Engine e3config.xml", idx.basename("e3config.xml"), 3))
        f.display_name = "PTC Arbortext Editor + Publishing Engine"
        f.archetype = ["A", "E"]
        f.note("e3config.xml carries the AllowedFunctions allowlist. Read it to learn which PE "
               "functions this site permits BEFORE attempting a call - PE access is governed by "
               "that allowlist, not by credentials.")
    if os.environ.get("APTCUSTOM"):
        f.add(ev("env", "APTCUSTOM=%s" % os.environ["APTCUSTOM"], weight=3))
    for root in installs.get("arbortext", []):
        f.add(ev("install", "installation at %s" % root, weight=3))
    cache = os.path.join(os.environ.get("LOCALAPPDATA", ""), "PTC", "Arbortext", "Editor")
    if os.environ.get("LOCALAPPDATA") and os.path.isdir(cache):
        f.add(ev("cache", "Arbortext editor cache at %s" % cache, weight=2))
    if f.score:
        f.note("Arbortext PE exposes f=acl, f=java, f=javascript, f=vbscript, f=convert, f=init "
               "and f=status. There is no f=compose - publishing goes out as "
               "f=java&class=com.arbortext.e3c.Application. PE composes via the Arbortext "
               "Formatting Engine, not DITA-OT, so its output will differ from a local DITA-OT "
               "build by design.")
    return f if f.score else None


def detect_xmetal(idx, installs):
    f = Finding("xmetal", "XMetaL Author Enterprise", ["A"])
    # The INI is versioned - xmetal60.ini, not xmetal.ini.
    ini = idx.basename_re(r"xmetal\d*\.ini")
    if ini:
        f.add(ev("file", "XMetaL INI file", ini, 4))
    for e, label in ((".ctm", "customization"), (".mcr", "macro"), (".xac", "compiled customization"),
                     (".rlx", "compiled rules")):
        if idx.ext(e):
            f.add(ev("ext", "%d XMetaL %s file(s) (%s)" % (idx.ext(e), label, e),
                     idx.ext_samples(e), 2))
    if idx.basename("xmetal.lic"):
        f.add(ev("licence", "XMetaL licence file", idx.basename("xmetal.lic"), 2))
    for root in installs.get("xmetal", []):
        f.add(ev("install", "installation or shared data at %s" % root, weight=3))
    if f.score:
        f.note("XMetaL 20.0 bundles DITA-OT 4.2.2 XM - newer than every cloud CCMS surveyed "
               "(IXIA 2.5.4, AEM 3.3.2, Heretto caps at 3.7.4). This team is closer to "
               "docs-as-code than they probably believe.")
        f.note("Windows-only, and automation is in-process COM/macro only. There is no headless "
               "build. DAC automates downstream of the save.")
    return f if f.score else None


def detect_framemaker(idx, installs):
    f = Finding("framemaker", "Adobe FrameMaker", ["A", "C"])
    binary = idx.ext(".fm") + idx.ext(".book") + idx.ext(".mif")
    if binary:
        f.add(ev("ext", "%d binary FrameMaker file(s) (.fm/.book/.mif)" % binary,
                 idx.ext_samples(".fm", ".book", ".mif"), 4))
    if idx.ext(".sts"):
        f.add(ev("ext", "%d style-mapping file(s) (.sts)" % idx.ext(".sts"),
                 idx.ext_samples(".sts"), 2))
        f.note(".sts is a style-mapping file for unstructured-to-DITA conversion, not a "
               "publishing settings artefact.")
    if idx.basename("structapps.fm"):
        f.add(ev("file", "structured application definitions (structapps.fm)",
                 idx.basename("structapps.fm"), 3))
    for root in installs.get("framemaker", []):
        f.add(ev("install", "installation at %s" % root, weight=2))
    if not f.score:
        return None
    # The discriminator that decides the archetype.
    dita_on_disk = idx.ext(".dita", ".ditamap", ".bookmap")
    if binary and dita_on_disk:
        f.archetype = ["A", "C"]
        f.note("Both binary .fm/.book AND DITA XML are present - likely mid-migration. The DITA "
               "portion is archetype A and can be pipelined now; the binary portion cannot get "
               "semantic diffs or component reuse.")
    elif binary:
        f.archetype = ["C"]
        f.note("Working tree is binary .fm/.book, so this is archetype C despite FrameMaker being "
               "a DITA-capable tool. Adobe states you cannot round-trip a DITA map to book "
               "conversion. Git, CI, linting and automated publishing are reachable; semantic "
               "diffs and component reuse are not.")
    else:
        f.archetype = ["A"]
        f.note("Structured content is saved as DITA XML, so this is archetype A - the full "
               "pipeline is available.")
    return f


def detect_flare(idx):
    f = Finding("madcap-flare", "MadCap Flare", ["C"])
    if idx.ext(".flprj"):
        f.add(ev("ext", "%d Flare project file(s) (.flprj)" % idx.ext(".flprj"),
                 idx.ext_samples(".flprj"), 5))
    for e, label in ((".fltoc", "TOC"), (".fltar", "target"), (".flskn", "skin"),
                     (".flvar", "variable set"), (".flmsp", "master page"),
                     (".flpgl", "page layout")):
        if idx.ext(e):
            f.add(ev("ext", "%d Flare %s file(s) (%s)" % (idx.ext(e), label, e),
                     idx.ext_samples(e), 1))
    if idx.dirname("Content") and idx.dirname("Project"):
        f.add(ev("dir", "Flare Content/ + Project/ layout",
                 idx.dirname("Content") + idx.dirname("Project"), 2))
    if not f.score:
        return None
    f.note("Flare source is XHTML .htm topics, NOT DITA. Do not build a DITA pipeline against it.")
    f.note("Flare has first-class native Git, Perforce, SVN and TFS integration, with branching "
           "supported in the UI for Git. This team very likely already has version control - "
           "what they lack is semantic diffs and component reuse, not source control.")
    leaked = []
    for d in ("Output", "Analyzer", "FileSync"):
        leaked += idx.pruned(d)
    if leaked:
        f.note("Generated Flare directories are present in the tree (%s). Flare's own .gitignore "
               "excludes Analyzer, FileSync, Output and Project/Users - if these are committed, "
               "the ignore list is wrong." % ", ".join(sorted(set(leaked))[:4]))
    f.note("CI hazard: Flare deactivates itself when a VM hardware fingerprint changes. "
           "'madbuild -activate' exists but works only on enterprise floating licences, and needs "
           "a license.json in the Flare Desktop.app folder. Pin the runner or budget for the "
           "floating licence.")
    return f


def detect_ixia(idx, installs):
    f = Finding("ixia-ccms", "MadCap IXIA CCMS (formerly IXIASOFT)", ["B"])
    for p in idx.basename("preferences.properties"):
        body = read_head(os.path.join(idx.root, p), 32768)
        if "textml" in body.lower() or "outputgenerator" in body.lower():
            f.add(ev("file", "IXIA preferences.properties with TEXTML/Output Generator topology",
                     [p], 5))
    for e in (".indexedcontent", ".customproperties"):
        if idx.ext(e):
            f.add(ev("ext", "%d IXIA export sidecar file(s) (%s)" % (idx.ext(e), e),
                     idx.ext_samples(e), 4))
    for name in ("importmanager.xml", "cmsserverservice.config", "outputtypes.xml",
                 "preprocessors.xml", "conductor-ixia.xml"):
        if idx.basename(name):
            f.add(ev("file", "IXIA server config %s" % name, idx.basename(name), 3))
    for root in installs.get("ixia", []):
        f.add(ev("install", "CCMS client/server at %s" % root, weight=3))
    if not f.score:
        return None
    f.note("Only unreleased or locked content lives on disk. Released content sits in the "
           "server-side TEXTML Content Store, so a filesystem scan sees a fraction of the corpus.")
    f.note("MadCap explicitly does not recommend exporting to edit externally and re-importing: "
           "'The re-import is an overwrite, not a merge.' One-way CCMS -> Git only.")
    f.note("MadCap states the API does not cover all CCMS functionality, is not guaranteed "
           "backward compatible across releases, is read-only for configuration, and that API "
           "support comes out of billable Customer Care hours.")
    f.note("Probe hazard: invalid credentials return HTTP 200 with error code -10021. A probe that "
           "only checks status codes will report a false success.")
    f.note("Output Generator packages DITA-OT 2.5.4 and needs Java JDK 11. That is roughly nine "
           "years behind current DITA-OT - expect CCMS and local builds to diverge.")
    return f


def detect_heretto(idx):
    f = Finding("heretto", "Heretto CCMS (formerly easyDITA / Jorsek)", ["B", "E"])
    hits, terms = [], []
    # .md is deliberately excluded: prose discussing a CCMS is not evidence of its use.
    for path in idx.iter_files_with_ext(
            {".xml", ".json", ".yml", ".yaml", ".properties", ".sh", ".cfg", ".bat"}, cap=900):
        body = read_head(path, 16384).lower()
        for term in ("heretto.com", "ezdnxtgen", "easydita", "jorsek"):
            if term in body:
                hits.append(idx.rel(path))
                terms.append(term)
                break
        if len(hits) >= SAMPLE_CAP:
            break
    if hits:
        f.add(ev("content", "Heretto references found (%s)" % ", ".join(sorted(set(terms))),
                 hits, 4))
    if not f.score:
        return None
    f.note("The v2 REST API is publishing-only and self-labelled Alpha. The v1 endpoints that "
           "actually read content are documented 'upon request' via a Customer Success Manager - "
           "so the blocker is a CSM request, not an admin key.")
    f.note("Webhooks, specifically NotifyPull, are the sanctioned way to get DITA source out. They "
           "may need enabling by your CSM.")
    f.note("Heretto states it does not provide general WebDAV support - WebDAV exists only for "
           "Oxygen connections. Do not build an export on it.")
    f.note("DITA-OT Cloud supports 2.5.4 through 3.7.4 only, against current local DITA-OT 4.4.1. "
           "This is the most common cause of 'it builds in the CCMS but not on my laptop'.")
    return f


def detect_tridion(idx):
    f = Finding("tridion-docs", "RWS Tridion Docs", ["B", "E"])
    hits, terms = [], []
    for path in idx.iter_files_with_ext(
            {".ps1", ".psm1", ".xml", ".json", ".config", ".yml", ".yaml"}, cap=900):
        body = read_head(path, 16384)
        for term in ("/ISHWS/", "FISHPUBSTATUS", "ISHRemote", "New-IshSession", "Trisoft",
                     "InfoShare"):
            if term.lower() in body.lower():
                hits.append(idx.rel(path))
                terms.append(term)
                break
        if len(hits) >= SAMPLE_CAP:
            break
    if hits:
        f.add(ev("content", "Tridion Docs references (%s)" % ", ".join(sorted(set(terms))), hits, 4))
    if idx.basename("publish.wsf"):
        f.add(ev("file", "Publish.wsf", idx.basename("publish.wsf"), 2))
    if not f.score:
        return None
    f.note("ISHRemote (PowerShell) is the de-facto CLI and is RWS-maintained. Auth on 15.x is "
           "OpenID Connect - client credentials or PKCE. Supplying username/password against 15.x "
           "fails with invalid_client.")
    f.note("Publishing is triggered by writing FISHPUBSTATUS metadata and then polling it. There "
           "is no documented completion callback.")
    return f


def detect_aem_guides(idx):
    f = Finding("aem-guides", "Adobe Experience Manager Guides", ["B"])
    uuid_named = idx.basename_re(r"guid-[0-9a-f\-]{8,}.*\.(dita|ditamap|xml)$")
    if uuid_named:
        f.add(ev("filename", "UUID-named DITA files (GUID-* pattern)", uuid_named, 5))
    fmdita = [p for p in idx.dirname("fmdita")] + idx.basename("ui_config.json")
    if fmdita:
        f.add(ev("path", "fmdita artefacts", fmdita, 3))
    if not f.score:
        return None
    f.note("CRITICAL: in UUID builds all content references are UUID-based and path independent. "
           "A filename- or path-based link checker will pass clean on genuinely broken links. "
           "Link integrity must be checked against UUID resolution instead.")
    f.note("AEM Guides ships DITA-OT 3.3.2, but Native PDF (CSS-based) is the DEFAULT PDF method "
           "in current versions - so the reference PDF is not a DITA-OT product at all and a local "
           "DITA-OT build will never match it.")
    f.note("The Git Connector (2026.08) imports Git INTO AEM. It is not a CCMS-to-Git mirror.")
    f.note("Cloud auth is Adobe IMS OAuth Server-to-Server (Bearer + X-Api-Key), provisioned in "
           "the Adobe Developer Console. This is an Adobe-admin task, not writer self-serve.")
    return f


def detect_paligo(idx):
    f = Finding("paligo", "Paligo", ["B"])
    if os.environ.get("PALIGO_API_KEY") or os.environ.get("PALIGO_USERNAME"):
        f.add(ev("env", "PALIGO_* environment variables present", weight=3))
    pub = idx.basename_re(r"publication--[a-z]{2}(-[a-z]{2})?\.xml")
    if pub:
        f.add(ev("filename", "Paligo publication--<lang>.xml export layout", pub, 4))
    docbook_hits = []
    for path in idx.iter_files_with_ext({".xml"}, cap=400):
        body = read_head(path, 4096)
        if "docbook.org/ns/docbook" in body or "DTD DocBook V5.1" in body:
            docbook_hits.append(idx.rel(path))
            if len(docbook_hits) >= SAMPLE_CAP:
                break
    if docbook_hits:
        f.add(ev("content", "DocBook 5.1 namespace in XML source", docbook_hits, 5))
    if not f.score:
        return None
    f.note("Paligo is DocBook 5.1, NOT DITA. Paligo's own documentation says so. Do not build a "
           "DITA pipeline against this content.")
    f.note("The API requires an admin user - 'The Paligo user must be an admin user', no "
           "exceptions, and licence permissions carry into the API. This is a hard wall, not a "
           "degradation.")
    f.note("The GitHub integration uploads published output AS A ZIP FILE. It is a deployment "
           "hook, not source control, and gives no diffable history.")
    f.note("The DocBook 5.1 publish output is lossy: it contains no metadata and no information "
           "about text fragments or variables. GET /documents/{id} returns higher-fidelity source.")
    return f


def detect_componize(idx):
    f = Finding("componize", "Componize (Alfresco)", ["B"])
    if idx.basename("alfresco-global.properties"):
        f.add(ev("file", "alfresco-global.properties", idx.basename("alfresco-global.properties"), 4))
    if idx.ext(".xpl"):
        f.add(ev("ext", "%d XProc pipeline(s) (.xpl)" % idx.ext(".xpl"), idx.ext_samples(".xpl"), 2))
    if not f.score:
        return None
    f.note("Componize's REST and Java APIs are advertised but no public endpoint reference exists. "
           "Treat as unverified and probe. CMIS is the realistic export protocol.")
    return f


def detect_author_it(idx):
    f = Finding("author-it", "Author-it", ["C"])
    if idx.ext(".ait"):
        f.add(ev("ext", "%d Author-it file(s) (.ait)" % idx.ext(".ait"), idx.ext_samples(".ait"), 4))
    if idx.basename("authorit.xsd"):
        f.add(ev("file", "AuthorIT.xsd", idx.basename("authorit.xsd"), 4))
    hits = idx.basename_re(r"author-it objects\.xml")
    if hits:
        f.add(ev("file", "Author-it XML export", hits, 4))
    if not f.score:
        return None
    f.note("Author-it is a proprietary relational database, not DITA and not XML-native. Export is "
           "a UI operation; the automation surface is outbound only (HTTP Post after-publish, and "
           "AION JSON, which is free in every subscription).")
    return f


def detect_fluid_topics(idx):
    f = Finding("fluid-topics", "Fluid Topics", ["D"])
    hits = []
    for path in idx.iter_files_with_ext(
            {".yml", ".yaml", ".sh", ".json", ".toml", ".cfg", ".py"}, cap=900):
        body = read_head(path, 16384)
        if ("Ft-Calling-App" in body or "fluidtopics.net" in body.lower()
                or "api/admin/khub" in body or "ftpub " in body):
            hits.append(idx.rel(path))
            if len(hits) >= SAMPLE_CAP:
                break
    if hits:
        f.add(ev("content", "Fluid Topics integration references", hits, 4))
    if idx.ext(".ftmap"):
        f.add(ev("ext", "%d .ftmap file(s)" % idx.ext(".ftmap"), idx.ext_samples(".ftmap"), 3))
    if not f.score:
        return None
    f.note("Publishing needs only the CONTENT_PUBLISHER role - KHUB_ADMIN is required only to "
           "CREATE a source. Ask for the smaller permission.")
    f.note("The Ft-Calling-App header is mandatory. A permission failure returns 404, not 403, so "
           "do not misdiagnose it as a wrong URL.")
    f.note("Limits: upload <= 1.85 GB, single topic <= 100 MB. There is a real CLI, ftpub.")
    return f


def detect_zoomin(idx):
    # Deliberately narrow. A bare "zoomin" substring matches prose *about* the product
    # (including DAC's own reference files) and also occurs inside unrelated words.
    # Require a host or an attribution string that only appears in a real deployment.
    hits = []
    for path in idx.iter_files_with_ext({".yml", ".yaml", ".json", ".txt", ".html", ".xml"}, cap=600):
        body = read_head(path, 16384)
        low = body.lower()
        if "zoominsoftware.io" in low or "powered by zoomin" in low:
            hits.append(idx.rel(path))
            if len(hits) >= SAMPLE_CAP:
                break
    if not hits:
        return None
    f = Finding("zoomin", "Zoomin (Salesforce)", ["D"])
    f.add(ev("content", "Zoomin references", hits, 3))
    f.note("MIGRATION RISK, not a delivery target. Salesforce completed the acquisition in "
           "November 2024 and ended renewals on 1 September 2025 for the documentation portal, "
           "In-Product Help, the API and Headless. Existing contracts are being honoured, some "
           "into 2026. Do not invest in this as a publish destination.")
    return f


def detect_local_dita_ot(idx):
    # A toolchain finding, not a content finding. Having the toolkit installed tells you
    # nothing about whether this folder contains anything to build.
    f = Finding("dita-ot", "DITA Open Toolkit (local)", [], kind="toolchain")
    which = shutil.which("dita")
    if which:
        f.add(ev("path", "dita on PATH at %s" % which, weight=4))
    if os.environ.get("DITA_HOME"):
        f.add(ev("env", "DITA_HOME=%s" % os.environ["DITA_HOME"], weight=3))
    local = idx.basename_re(r"dita-ot-\d+.*")
    dirs = [d for d in idx.dirnames if d.startswith("dita-ot-")]
    if dirs:
        f.add(ev("dir", "local DITA-OT directory", [p for d in dirs for p in idx.dirname(d)], 2))
    elif local:
        f.add(ev("file", "DITA-OT artefacts", local, 1))
    return f if f.score else None


# --------------------------------------------------------------------------------------
# Incumbent tooling - what already exists and must be extended, not overwritten
# --------------------------------------------------------------------------------------


def detect_incumbent(idx):
    inc = {
        "vcs": None, "ci": [], "hooks": [], "formatters": [], "quality_gates": [],
        "build_wrappers": [], "project_files": [], "catalogs": [], "notes": [],
    }
    if os.path.isdir(os.path.join(idx.root, ".git")):
        inc["vcs"] = "git"
    elif idx.pruned(".svn"):
        inc["vcs"] = "svn"
    elif idx.pruned(".hg"):
        inc["vcs"] = "mercurial"

    wf_dir = os.path.join(idx.root, ".github", "workflows")
    if os.path.isdir(wf_dir):
        try:
            for fn in sorted(os.listdir(wf_dir)):
                if fn.endswith((".yml", ".yaml")):
                    body = read_head(os.path.join(wf_dir, fn), 65536)
                    entry = {"path": ".github/workflows/%s" % fn, "runner": "github-actions"}
                    if "dita-ot-action" in body:
                        entry["uses_dita_ot_action"] = True
                    if "dita" in body.lower():
                        entry["mentions_dita"] = True
                    inc["ci"].append(entry)
        except OSError:
            pass
    if idx.basename(".gitlab-ci.yml"):
        inc["ci"].append({"path": ".gitlab-ci.yml", "runner": "gitlab-ci"})
    for name, runner in (("azure-pipelines.yml", "azure"), ("Jenkinsfile", "jenkins"),
                         ("bitbucket-pipelines.yml", "bitbucket"), (".teamcity", "teamcity")):
        if idx.basename(name) or idx.dirname(name):
            inc["ci"].append({"path": name, "runner": runner})

    if idx.dirname(".husky"):
        inc["hooks"].append({"path": ".husky", "kind": "husky"})
    hooks_dir = os.path.join(idx.root, ".git", "hooks")
    if os.path.isdir(hooks_dir):
        try:
            live = [h for h in os.listdir(hooks_dir) if not h.endswith(".sample")]
            if live:
                inc["hooks"].append({"path": ".git/hooks", "kind": "git-native",
                                     "hooks": sorted(live)[:8]})
        except OSError:
            pass

    for name in (".prettierrc", ".prettierrc.yml", ".prettierrc.yaml", ".prettierrc.json",
                 "prettier.config.js", ".editorconfig", ".gitattributes"):
        if idx.basename(name):
            inc["formatters"].append({"path": name})
    pj = idx.basename("package.json")
    if pj:
        body = read_head(os.path.join(idx.root, pj[0]), 65536)
        entry = {"path": pj[0]}
        if "@prettier/plugin-xml" in body:
            entry["prettier_plugin_xml"] = True
        if "lint-staged" in body:
            entry["lint_staged"] = True
        if "husky" in body:
            entry["husky"] = True
        inc["formatters"].append(entry)

    if idx.basename(".vale.ini") or idx.basename("vale.ini"):
        inc["quality_gates"].append({"path": ".vale.ini", "kind": "vale"})
    if idx.ext(".sch"):
        inc["quality_gates"].append({"kind": "schematron", "count": idx.ext(".sch"),
                                     "samples": idx.ext_samples(".sch")})
    if idx.ext(".ditaval"):
        inc["quality_gates"].append({"kind": "ditaval", "count": idx.ext(".ditaval"),
                                     "samples": idx.ext_samples(".ditaval")})

    for name, kind in (("build.gradle", "gradle"), ("build.gradle.kts", "gradle"),
                       ("gradlew", "gradle-wrapper"), ("pom.xml", "maven"),
                       ("build.xml", "ant"), ("Makefile", "make")):
        hit = idx.basename(name)
        if hit:
            entry = {"path": hit[0], "kind": kind}
            if kind.startswith("gradle") and name.startswith("build.gradle"):
                body = read_head(os.path.join(idx.root, hit[0]), 65536)
                # Match the declared plugin id, not a bare substring. dita-ot/docs names
                # eerohele in a comment explaining what it replaced, which would otherwise
                # produce a false "you are on the dead plugin" warning.
                plugin_ids = re.findall(
                    r"""id\s*[\('"]+\s*([A-Za-z0-9_.\-]*dita-ot[A-Za-z0-9_.\-]*)""", body)
                if plugin_ids:
                    entry["dita_ot_gradle"] = True
                    entry["plugin_ids"] = sorted(set(plugin_ids))
                    if any("eerohele" in p for p in plugin_ids):
                        entry["plugin_variant"] = "eerohele (abandoned since 2021)"
                    elif any("jyjeanne" in p for p in plugin_ids):
                        entry["plugin_variant"] = "io.github.jyjeanne (current)"
                    else:
                        entry["plugin_variant"] = "unrecognised"
                elif "dita-ot-gradle" in body:
                    entry["dita_ot_gradle"] = True
                    entry["plugin_variant"] = "unrecognised"
                if "mavenCentral" in body:
                    entry["needs_maven_central"] = True
                if ".ditaval" in body:
                    entry["references_ditaval"] = True
            inc["build_wrappers"].append(entry)

    # Hand-rolled publish scripts. This is the most common pre-docs-as-code state: one
    # person's shell script with absolute paths and a hardcoded toolkit directory. It
    # works on exactly one machine, and the pinned version is often years old, so it is
    # both a strong signal and a concrete finding.
    rx_ditaot_ver = re.compile(r"DITA[-_ ]?OT[-_ ]?(\d+\.\d+(?:\.\d+)?)", re.I)
    rx_abs_path = re.compile(
        r"""=\s*["']?(/(?:Library|Users|home|opt|var|Applications)/[^\s"']*)""")
    for path in idx.iter_files_with_ext({".sh", ".bat", ".cmd", ".ps1"}, cap=200):
        body = read_head(path, 32768)
        if "dita" not in body.lower():
            continue
        entry = {"path": idx.rel(path), "kind": "hand-rolled-script"}
        vers = sorted(set(rx_ditaot_ver.findall(body)))
        if vers:
            entry["hardcoded_dita_ot_versions"] = vers
        abs_paths = sorted(set(rx_abs_path.findall(body)))[:4]
        if abs_paths:
            entry["absolute_paths"] = abs_paths

        # Custom transtypes and plugins. A build that names a transtype which is not a
        # DITA-OT built-in depends on a plugin, and if that plugin is not in this
        # repository then any generated CI will either fail or - far worse - silently
        # build stock HTML5 and produce convincingly wrong output.
        builtin = {"dita", "eclipsehelp", "html5", "htmlhelp", "markdown",
                   "markdown_gitbook", "markdown_github", "pdf", "pdf2", "xhtml",
                   "troff", "tocjs", "preprocess", "validate"}
        # Match per line and only where the line actually invokes dita. Scanning the whole
        # body catches unrelated tools that also take -f, such as `ant -f integrator.xml`.
        transtypes = set()
        for line in body.splitlines():
            if "dita" not in line.lower():
                continue
            transtypes.update(re.findall(r"(?:-f|--format=)\s*([A-Za-z0-9_.\-]+)", line))
        custom = sorted(t for t in transtypes
                        if t.lower() not in builtin
                        and not t.lower().endswith((".xml", ".properties", ".ditamap", ".sh")))
        if custom:
            entry["custom_transtypes"] = custom
            entry["plugin_in_repo"] = any(idx.basename("plugin.xml"))
        inc["build_wrappers"].append(entry)

    for name in ("dita-ot-project.xml",):
        if idx.basename(name):
            inc["project_files"].append({"path": idx.basename(name)[0], "kind": "dita-ot-project"})
    for name in ("catalog.xml", "catalog-dita.xml"):
        if idx.basename(name):
            inc["catalogs"].append({"path": idx.basename(name)[0]})

    if inc["ci"]:
        inc["notes"].append("CI already exists. Extend it - do not write a second workflow, or the "
                            "repo gets duplicate builds.")
    if inc["hooks"]:
        inc["notes"].append("Pre-commit hooks already exist. They may reject DAC's own commits if "
                            "DAC reformats source. Adopt the existing hook chain.")
    if any(f.get("prettier_plugin_xml") for f in inc["formatters"]):
        inc["notes"].append("@prettier/plugin-xml is already configured - XML diff normalisation "
                            "is solved here. Do not change the config.")
    if not inc["vcs"]:
        inc["notes"].append("No version control at all. The highest-value first action is git init.")
    return inc


# --------------------------------------------------------------------------------------
# DITA content statistics
# --------------------------------------------------------------------------------------


def dita_statistics(idx):
    stats = {
        "maps": idx.ext(".ditamap"), "bookmaps": idx.ext(".bookmap"),
        "topics": idx.ext(".dita"), "ditavals": idx.ext(".ditaval"),
        "conref_files": 0, "keyref_files": 0, "subjectscheme_files": 0,
        "markdown_topicrefs": 0, "uuid_named": 0,
        "conref_samples": [], "keyref_samples": [], "subjectscheme_samples": [],
        "markdown_topicref_samples": [], "files_scanned": 0,
    }
    rx_conref = re.compile(r"\bcon(?:key)?ref\s*=")
    rx_keyref = re.compile(r"\b(?:con)?keyref\s*=")
    rx_subject = re.compile(r"<subjectScheme", re.I)
    rx_mdformat = re.compile(r"format\s*=\s*[\"'](?:markdown|md|mdita|hdita)[\"']", re.I)
    rx_uuid = re.compile(r"^GUID-[0-9a-f\-]{8,}", re.I)

    for path in idx.iter_files_with_ext({".dita", ".ditamap", ".bookmap"}):
        stats["files_scanned"] += 1
        rel = idx.rel(path)
        if rx_uuid.match(os.path.basename(path)):
            stats["uuid_named"] += 1
        body = read_head(path)
        if rx_conref.search(body):
            stats["conref_files"] += 1
            if len(stats["conref_samples"]) < SAMPLE_CAP:
                stats["conref_samples"].append(rel)
        if rx_keyref.search(body):
            stats["keyref_files"] += 1
            if len(stats["keyref_samples"]) < SAMPLE_CAP:
                stats["keyref_samples"].append(rel)
        if rx_subject.search(body):
            stats["subjectscheme_files"] += 1
            if len(stats["subjectscheme_samples"]) < SAMPLE_CAP:
                stats["subjectscheme_samples"].append(rel)
        if rx_mdformat.search(body):
            stats["markdown_topicrefs"] += 1
            if len(stats["markdown_topicref_samples"]) < SAMPLE_CAP:
                stats["markdown_topicref_samples"].append(rel)
    return stats


# --------------------------------------------------------------------------------------
# Warnings - correctness hazards worth surfacing before any setup runs
# --------------------------------------------------------------------------------------


def detect_custom_grammars(idx):
    """Repo-local DITA grammars that override the ones shipped inside DITA-OT.

    This is the single most dangerous case for an automated setup tool. A repo carrying its
    own doctypes expects the build to replace DITA-OT's bundled grammars with them. A naive
    build succeeds against the STALE BUNDLED GRAMMARS and reports green while validating
    against the wrong schema entirely - a silent wrong answer rather than a failure.
    """
    dtd = idx.ext(".dtd")
    rng = idx.ext(".rng")
    mod = idx.ext(".mod")
    ent = idx.ext(".ent")
    if not (dtd or rng or mod or ent):
        return None
    doctype_dirs = idx.dirname("doctypes") + idx.dirname("dtd") + idx.dirname("rng") \
        + idx.dirname("grammars") + idx.dirname("schema")
    return {
        "dtd": dtd, "rng": rng, "mod": mod, "ent": ent,
        "doctype_dirs": doctype_dirs,
        "rng_primary": rng > dtd,
        "samples": idx.ext_samples(".rng", ".dtd", ".mod", ".ent"),
    }


LICENCE_PERMISSIVE = ("apache license", "mit license", "permission is hereby granted",
                      "bsd", "creative commons", "mozilla public license", "gnu general public",
                      "eclipse public license", "unlicense")


def detect_licence(idx):
    """Whether the repository carries a recognisable open-source licence.

    DAC must never add a LICENSE file, rewrite headers, or configure a push remote on
    content whose licence it has not verified. Some very DITA-relevant corpora - the OASIS
    specification source among them - are publicly readable but governed by terms that do
    not permit redistribution.
    """
    hits = []
    for name in ("license", "license.md", "license.txt", "licence", "licence.md",
                 "licence.txt", "copying", "copying.md", "notice", "notice.md"):
        hits.extend(idx.basename(name))
    if not hits:
        return {"present": False, "permissive": False, "files": [], "note": "no licence file"}
    body = ""
    for rel in hits[:3]:
        body += read_head(os.path.join(idx.root, rel), 16384).lower()
    permissive = any(marker in body for marker in LICENCE_PERMISSIVE)
    restricted_markers = ("oasis ipr policy", "rf on limited terms", "all rights reserved",
                          "noassertion")
    restricted = any(m in body for m in restricted_markers)
    return {
        "present": True,
        "permissive": bool(permissive and not restricted),
        "restricted_signals": [m for m in restricted_markers if m in body],
        "files": hits[:3],
    }


def build_warnings(idx, stats, incumbent, findings, grammars=None, licence=None):
    w = []
    vendors = {f["vendor"] for f in findings}

    if grammars:
        kinds = []
        for k, label in (("rng", "RELAX NG"), ("dtd", "DTD"), ("mod", "DTD module"),
                         ("ent", "entity")):
            if grammars[k]:
                kinds.append("%d %s file(s)" % (grammars[k], label))
        w.append({
            "id": "WARN-custom-grammars",
            "severity": "high",
            "text": "This repository carries its own DITA grammars (%s%s). A build that does "
                    "not install them over the grammars bundled inside DITA-OT will validate "
                    "against the WRONG SCHEMA and still report success. That is a silent wrong "
                    "answer, not a failure, and it is the most dangerous case for an automated "
                    "setup tool. Read the existing build before generating a new one, and "
                    "replicate however it overrides the bundled doctypes."
                    % (", ".join(kinds),
                       "; doctype directories: " + ", ".join(grammars["doctype_dirs"][:3])
                       if grammars["doctype_dirs"] else ""),
        })
        if grammars["rng_primary"]:
            w.append({
                "id": "WARN-rng-needs-jing",
                "severity": "medium",
                "text": "The grammars here are primarily RELAX NG rather than DTD. xmllint is "
                        "not a dependable RELAX NG validator, so a generated xmllint step would "
                        "give false confidence. Use jing for these files.",
            })

    if licence and not licence.get("permissive"):
        if not licence.get("present"):
            detail = "No licence file was found."
        else:
            sig = licence.get("restricted_signals") or []
            detail = ("A licence file exists but does not carry a recognisable permissive "
                      "open-source grant%s." % (" (found: %s)" % ", ".join(sig) if sig else ""))
        w.append({
            "id": "WARN-licence-unverified",
            "severity": "medium",
            "text": "%s Do NOT add a LICENSE file, rewrite file headers, or configure a push "
                    "remote for this content. Some DITA corpora are publicly readable but "
                    "governed by terms that forbid redistribution - the OASIS specification "
                    "source is one. Repository setup must be a no-op here until a human "
                    "confirms the terms." % detail,
        })

    # A ditaval is "wired" if a project file declares it, or a build wrapper or CI job
    # references it. dita-ot/docs applies filters from build.gradle rather than a
    # project file, and that is a legitimate configuration.
    ditaval_wired = bool(incumbent["project_files"]) or any(
        bw.get("references_ditaval") for bw in incumbent["build_wrappers"])
    if stats["ditavals"] and not ditaval_wired:
        w.append({
            "id": "WARN-ditaval-unfiltered",
            "severity": "high",
            "text": "%d .ditaval filter file(s) exist but nothing in the repo declares which "
                    "filter applies to which deliverable - no dita-ot-project.xml, and no build "
                    "wrapper references them. A build that omits --filter emits conditional "
                    "content into the wrong output and still exits zero. This is the "
                    "green-and-wrong failure class." % stats["ditavals"],
        })
    elif stats["ditavals"] and not incumbent["project_files"]:
        w.append({
            "id": "INFO-ditaval-in-build-script",
            "severity": "info",
            "text": "%d .ditaval file(s) are applied from a build script rather than a "
                    "dita-ot-project.xml. That works. Moving them into a project file makes "
                    "deliverables declarative data an agent can read and modify, instead of "
                    "build logic embedded in a script." % stats["ditavals"],
        })
    if stats["uuid_named"]:
        w.append({
            "id": "WARN-uuid-linkcheck",
            "severity": "high",
            "text": "%d UUID-named DITA file(s) found. Filename- and path-based link checking "
                    "silently passes on genuinely broken links when references are UUID-based. "
                    "Link integrity needs a UUID-aware checker." % stats["uuid_named"],
        })
    if stats["markdown_topicrefs"]:
        w.append({
            "id": "INFO-markdown-topicrefs",
            "severity": "info",
            "text": "%d file(s) reference Markdown or HDITA topics with an explicit @format. Note "
                    "that DITA-OT ignores the file extension - @format is mandatory or the file is "
                    "not recognised at all. Keys cannot be defined in Markdown topicrefs."
                    % stats["markdown_topicrefs"],
        })
    if not incumbent["catalogs"] and (stats["maps"] or stats["topics"]):
        w.append({
            "id": "WARN-no-catalog",
            "severity": "medium",
            "text": "No XML catalog found in the repo. DITA files reference public identifiers, so "
                    "validation without XML_CATALOG_FILES pointing at the DITA-OT catalog either "
                    "fails or silently fetches DTDs over HTTP.",
        })
    for bw in incumbent["build_wrappers"]:
        if bw.get("plugin_variant", "").startswith("eerohele"):
            w.append({
                "id": "WARN-dead-gradle-plugin",
                "severity": "medium",
                "text": "The build uses eerohele/dita-ot-gradle, whose last release was v0.7.1 and "
                        "last commit January 2021. The maintained successor is "
                        "io.github.jyjeanne.dita-ot-gradle, which DITA-OT's own docs repo uses.",
            })
        if bw.get("kind") == "hand-rolled-script":
            bits = []
            if bw.get("hardcoded_dita_ot_versions"):
                bits.append("pins DITA-OT %s" % ", ".join(bw["hardcoded_dita_ot_versions"]))
            if bw.get("absolute_paths"):
                bits.append("hardcodes machine-specific paths (%s)"
                            % ", ".join(bw["absolute_paths"][:2]))
            stale = [v for v in bw.get("hardcoded_dita_ot_versions", [])
                     if int(v.split(".")[0]) < 4]
            w.append({
                "id": "WARN-hand-rolled-build",
                "severity": "high" if stale else "medium",
                "text": "`%s` looks like a hand-written publish script%s. This is the most common "
                        "state before docs-as-code: it works on one person's machine, cannot run "
                        "unattended, and nothing verifies it still works.%s Replace it with a "
                        "checked-in build script plus a project file so the same command runs "
                        "locally and in CI."
                        % (bw["path"],
                           (" that " + " and ".join(bits)) if bits else "",
                           (" The pinned toolkit (%s) is several major versions behind the "
                            "current 4.4.1, so its output will differ from anything built today."
                            % ", ".join(stale)) if stale else ""),
            })
        if bw.get("custom_transtypes") and not bw.get("plugin_in_repo"):
            w.append({
                "id": "WARN-custom-plugin-missing",
                "severity": "high",
                "text": "`%s` builds with the transtype(s) %s, which are not DITA-OT built-ins, so "
                        "they come from a custom plugin. No plugin.xml exists in this repository, "
                        "meaning the plugin lives outside it and nothing here records which "
                        "version. Any generated pipeline will either fail outright or - far worse "
                        "- fall back to stock output that looks nothing like the published site, "
                        "while reporting success. Vendor the plugin into this repository, or "
                        "install it in CI by ID or zip with a pinned version, before automating "
                        "the build."
                        % (bw["path"], ", ".join("`%s`" % t for t in bw["custom_transtypes"])),
            })
        if bw.get("needs_maven_central"):
            w.append({
                "id": "WARN-maven-dependency",
                "severity": "medium",
                "text": "The build resolves dependencies from Maven Central. If the network probe "
                        "reports Maven Central blocked - common behind corporate artifact "
                        "firewalls - this build will fail in a way that looks like a network flake.",
            })
    if "paligo" in vendors and (stats["maps"] or stats["topics"]):
        w.append({
            "id": "WARN-mixed-docbook-dita",
            "severity": "medium",
            "text": "Both Paligo/DocBook and DITA signals are present. These need separate "
                    "pipelines - DocBook to DITA conversion is real XSLT work that DAC scopes but "
                    "does not perform.",
        })
    if idx.truncated:
        w.append({
            "id": "WARN-walk-truncated",
            "severity": "low",
            "text": "The tree exceeded %d files and the scan was truncated. Counts are lower "
                    "bounds." % MAX_FILES,
        })
    return w


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def run(root):
    idx = Index(root).build()
    installs = install_candidates()
    stats = dita_statistics(idx)

    candidates = [
        detect_native_dita(idx, stats),
        detect_local_dita_ot(idx),
        detect_oxygen(idx, installs),
        detect_content_fusion(idx),
        detect_arbortext(idx, installs),
        detect_xmetal(idx, installs),
        detect_framemaker(idx, installs),
        detect_flare(idx),
        detect_ixia(idx, installs),
        detect_heretto(idx),
        detect_tridion(idx),
        detect_aem_guides(idx),
        detect_paligo(idx),
        detect_componize(idx),
        detect_author_it(idx),
        detect_fluid_topics(idx),
        detect_zoomin(idx),
    ]
    findings = [c.to_dict() for c in candidates if c is not None]
    findings.sort(key=lambda f: f["score"], reverse=True)

    incumbent = detect_incumbent(idx)
    grammars = detect_custom_grammars(idx)
    licence = detect_licence(idx)
    warnings = build_warnings(idx, stats, incumbent, findings, grammars, licence)

    # Only content-bearing systems set the archetype.
    content_findings = [f for f in findings
                        if f.get("kind") == "content" and f["confidence"] in ("high", "medium")]
    archetypes = sorted({a for f in content_findings for a in f["archetype"]})

    # Is there anything here to work with at all? A writer whose content lives in a CCMS
    # opens an empty folder, and DAC must recognise that and switch to onboarding rather
    # than scoring an empty directory as though it were a real estate.
    has_source = bool(stats.get("maps") or stats.get("topics")
                      or idx.ext(".xml", ".htm", ".fm", ".book", ".ait"))
    content_found = bool(content_findings) and has_source
    if not content_found:
        warnings.insert(0, {
            "id": "WARN-no-content-found",
            "severity": "high",
            "text": "No documentation source was found in this folder (%d file(s) scanned). "
                    "This is expected and fine if your content lives in a CCMS, on a network "
                    "share, or in another repository - but it means DAC cannot assess or set "
                    "anything up until it knows where the content is. Do not treat the scores "
                    "below as meaningful. Answer the location question in the intake and run "
                    "again." % idx.total_files,
        })

    return {
        "dac_version": DAC_VERSION,
        "stage": "detect",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": idx.root,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "inventory": {
            "total_files": idx.total_files,
            "truncated": idx.truncated,
            "ext_counts": dict(sorted(idx.ext_counts.items(), key=lambda kv: -kv[1])[:40]),
            "walk_errors": idx.errors[:5],
            "skipped_dac_installs": idx.skipped_self,
        },
        "dita": stats,
        "archetypes": archetypes,
        "content_found": content_found,
        "onboarding_required": not content_found,
        "findings": findings,
        "incumbent": incumbent,
        "custom_grammars": grammars,
        "licence": licence,
        "warnings": warnings,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="DAC credential-free ecosystem detector")
    ap.add_argument("--root", default=".", help="directory to scan (default: cwd)")
    ap.add_argument("--out", help="write JSON here instead of stdout")
    ap.add_argument("--quiet", action="store_true", help="suppress the human-readable summary")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print("error: --root is not a directory: %s" % args.root, file=sys.stderr)
        return 2

    result = run(args.root)
    payload = json.dumps(result, indent=2)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        if not args.quiet:
            print("detect: wrote %s" % args.out, file=sys.stderr)
            print("  files scanned : %d" % result["inventory"]["total_files"], file=sys.stderr)
            print("  archetypes    : %s" % (", ".join(result["archetypes"]) or "none"),
                  file=sys.stderr)
            for f in result["findings"]:
                print("  %-9s %-46s %s" % (f["confidence"], f["display_name"],
                                           "/".join(f["archetype"])), file=sys.stderr)
            for wn in result["warnings"]:
                print("  ! %-8s %s" % (wn["severity"], wn["id"]), file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
