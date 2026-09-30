#!/usr/bin/env python3
"""ditacore - the operations a writer needs on their own DITA, as a library.

This is the shared engine behind all three interaction surfaces DAC installs:

    docs            a command line for humans
    mcp-server.py   typed tools for Cursor, Claude Code and Copilot
    api-server.py   JSON over HTTP for dashboards and integrations

All three call into here, so they cannot drift apart or disagree. Add an operation once and
every surface gets it.

Deliberately standard library only. A writer should never have to run `pip install`
to ask a question about their own documentation.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

CORE_VERSION = "0.1.0"

SKIP_DIRS = {".git", "out", "temp", "tmp", ".gradle", "node_modules", ".dac",
             "build", "dist", ".venv", "__pycache__"}

TOPIC_EXTS = (".dita", ".xml")
MAP_EXTS = (".ditamap", ".bookmap")

# Attributes that point at another resource. Each needs different resolution, which is why
# a single "find broken links" pass is not enough on its own.
DIRECT_REFS = ("href", "conref", "copy-to", "data-href")
KEY_REFS = ("keyref", "conkeyref", "keys")


# ----------------------------------------------------------------------------------------
# inventory
# ----------------------------------------------------------------------------------------


def _walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def find_files(root, exts):
    return sorted(p for p in _walk(root) if p.lower().endswith(tuple(exts)))


def find_maps(root):
    return find_files(root, MAP_EXTS)


def find_topics(root):
    """DITA topics. .xml files are included only if they look like DITA, because plenty of
    repositories carry unrelated XML."""
    out = []
    for p in find_files(root, TOPIC_EXTS):
        if p.lower().endswith(".dita"):
            out.append(p)
        else:
            head = read_head(p, 2048)
            if re.search(r"<!DOCTYPE\s+(topic|task|concept|reference|glossentry|troubleshooting)",
                         head, re.I) or re.search(r"DITA\s+(Topic|Task|Concept|Reference)", head):
                out.append(p)
    return out


def read_head(path, n=8192):
    try:
        with open(path, "rb") as fh:
            return fh.read(n).decode("utf-8", errors="replace")
    except OSError:
        return ""


def read_text(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def parse(path):
    """Parse a DITA file, tolerating the DTD declaration.

    ElementTree will try to fetch an external DTD, which is slow and fails offline, so the
    doctype is stripped before parsing. Entities defined in the DTD are lost, which is
    acceptable for structural queries.
    """
    text = read_text(path)
    if not text:
        return None, "empty or unreadable"
    text = re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", text, count=1, flags=re.S)
    try:
        return ET.fromstring(text), None
    except ET.ParseError as exc:
        return None, "not well-formed: %s" % exc


def topic_type(path):
    root, err = parse(path)
    if root is None:
        return "unknown"
    return root.tag.split("}")[-1]


def topic_title(path):
    root, err = parse(path)
    if root is None:
        return None
    for el in root.iter():
        if el.tag.split("}")[-1] == "title":
            return "".join(el.itertext()).strip()
    return None


# ----------------------------------------------------------------------------------------
# map structure
# ----------------------------------------------------------------------------------------


def map_tree(map_path, root=None, _seen=None, _depth=0):
    """Resolve a map into a nested tree, following mapref and topicref.

    Cycles are detected rather than followed, because a circular mapref would otherwise
    recurse until the stack gives out.
    """
    root = root or os.path.dirname(os.path.abspath(map_path))
    _seen = _seen or set()
    ap = os.path.abspath(map_path)
    node = {"path": os.path.relpath(ap, root), "kind": "map", "children": []}

    if ap in _seen:
        node["cycle"] = True
        return node
    _seen = _seen | {ap}

    if _depth > 40:
        node["error"] = "nesting deeper than 40 levels; stopped"
        return node

    el, err = parse(ap)
    if el is None:
        node["error"] = err
        return node
    node["title"] = (lambda t: t.strip() if t else None)(
        "".join(el.findtext("title") or ""))

    base = os.path.dirname(ap)

    def visit(parent_el, container):
        for child in list(parent_el):
            tag = child.tag.split("}")[-1]
            if tag not in ("topicref", "mapref", "topichead", "topicgroup", "chapter",
                           "appendix", "part", "frontmatter", "backmatter", "keydef"):
                continue
            href = child.get("href")
            fmt = (child.get("format") or "").lower()
            entry = {"kind": tag, "href": href, "format": fmt or None}
            if child.get("keys"):
                entry["keys"] = child.get("keys")
            if child.get("navtitle"):
                entry["navtitle"] = child.get("navtitle")

            if href and not href.startswith(("http://", "https://", "mailto:")):
                target = os.path.normpath(os.path.join(base, href.split("#")[0]))
                entry["resolved"] = os.path.relpath(target, root)
                entry["exists"] = os.path.exists(target)
                if entry["exists"] and (target.lower().endswith(MAP_EXTS)
                                        or fmt == "ditamap"):
                    sub = map_tree(target, root, _seen, _depth + 1)
                    entry["children"] = sub.get("children", [])
                    entry["title"] = sub.get("title")
                    entry["kind"] = "map"
                elif entry["exists"]:
                    entry["title"] = topic_title(target)
                    entry["type"] = topic_type(target)
            container.append(entry)
            if list(child):
                entry.setdefault("children", [])
                visit(child, entry["children"])

    visit(el, node["children"])
    return node


def flatten(node, out=None):
    out = out if out is not None else []
    for c in node.get("children", []):
        out.append(c)
        flatten(c, out)
    return out


def root_maps(root):
    """Maps that no other map references. These are the real entry points, and a repository
    with several is normal - one per deliverable."""
    maps = find_maps(root)
    referenced = set()
    for m in maps:
        base = os.path.dirname(m)
        for href in re.findall(r'href\s*=\s*"([^"]+)"', read_text(m)):
            if href.lower().split("#")[0].endswith(MAP_EXTS):
                referenced.add(os.path.normpath(os.path.join(base, href.split("#")[0])))
    return [m for m in maps if os.path.abspath(m) not in
            {os.path.abspath(r) for r in referenced}]


# ----------------------------------------------------------------------------------------
# keys and reuse
# ----------------------------------------------------------------------------------------


def list_keys(root):
    """Every key defined anywhere, with where it was defined.

    A key defined twice is reported, because the winner depends on map order and that is a
    genuine source of confusion.
    """
    keys = {}
    for m in find_maps(root):
        rel = os.path.relpath(m, root)
        text = read_text(m)
        for lineno, line in enumerate(text.splitlines(), 1):
            for km in re.finditer(r'\bkeys\s*=\s*"([^"]+)"', line):
                href = None
                hm = re.search(r'\bhref\s*=\s*"([^"]+)"', line)
                if hm:
                    href = hm.group(1)
                for key in km.group(1).split():
                    keys.setdefault(key, []).append(
                        {"map": rel, "line": lineno, "href": href})
    return keys


def resolve_key(root, key):
    defs = list_keys(root).get(key, [])
    result = {"key": key, "defined": bool(defs), "definitions": defs}
    if len(defs) > 1:
        result["warning"] = (
            "Defined %d times. Which one wins depends on map order, so this is worth "
            "resolving." % len(defs))
    if defs and defs[0].get("href"):
        base = os.path.dirname(os.path.join(root, defs[0]["map"]))
        target = os.path.normpath(os.path.join(base, defs[0]["href"].split("#")[0]))
        result["target"] = os.path.relpath(target, root)
        result["target_exists"] = os.path.exists(target)
    result["used_in"] = find_key_usages(root, key)
    return result


def find_key_usages(root, key):
    """Where a key is referenced. Answers "what breaks if I change this?"."""
    hits = []
    pat = re.compile(r'\b(?:conkeyref|keyref)\s*=\s*"%s(?:/[^"]*)?"' % re.escape(key))
    for p in find_topics(root) + find_maps(root):
        text = read_text(p)
        if key not in text:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                hits.append({"file": os.path.relpath(p, root), "line": lineno,
                             "text": line.strip()[:160]})
    return hits


def find_file_usages(root, target):
    """Everything that references a file. Run this BEFORE renaming or deleting anything."""
    target_abs = os.path.abspath(os.path.join(root, target))
    hits = []
    for p in find_topics(root) + find_maps(root):
        base = os.path.dirname(os.path.abspath(p))
        text = read_text(p)
        for lineno, line in enumerate(text.splitlines(), 1):
            for attr in DIRECT_REFS:
                for m in re.finditer(r'\b%s\s*=\s*"([^"]+)"' % attr, line):
                    href = m.group(1).split("#")[0]
                    if not href or href.startswith(("http://", "https://", "mailto:")):
                        continue
                    if os.path.normpath(os.path.join(base, href)) == target_abs:
                        hits.append({"file": os.path.relpath(p, root), "line": lineno,
                                     "attribute": attr})
    return hits


# ----------------------------------------------------------------------------------------
# link integrity, without needing Java
# ----------------------------------------------------------------------------------------


def check_links(root):
    """Resolve every reference statically and report what does not exist.

    This runs with no toolkit and no Java, which matters because it means a writer can check
    their work before they have installed anything. It is a complement to `dita validate`,
    not a replacement: this catches missing files and undefined keys, while the toolkit
    catches things only a full build can see.
    """
    problems = []
    keys = set(list_keys(root))
    files = find_topics(root) + find_maps(root)

    for p in files:
        rel = os.path.relpath(p, root)
        base = os.path.dirname(os.path.abspath(p))
        text = read_text(p)

        el, err = parse(p)
        if el is None and err and "not well-formed" in err:
            problems.append({"file": rel, "line": 1, "kind": "malformed",
                             "detail": err, "severity": "error"})
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            for attr in DIRECT_REFS:
                for m in re.finditer(r'\b%s\s*=\s*"([^"]+)"' % attr, line):
                    raw = m.group(1)
                    if raw.startswith(("http://", "https://", "mailto:", "#")):
                        continue
                    if raw.startswith("data:"):
                        continue
                    href = raw.split("#")[0]
                    if not href:
                        continue
                    target = os.path.normpath(os.path.join(base, href))
                    if not os.path.exists(target):
                        problems.append({
                            "file": rel, "line": lineno, "kind": "missing-target",
                            "attribute": attr, "target": raw, "severity": "error",
                            "detail": "%s points at %s, which does not exist"
                                      % (attr, raw)})

            for m in re.finditer(r'\b(conkeyref|keyref)\s*=\s*"([^"]+)"', line):
                attr, val = m.group(1), m.group(2)
                key = val.split("/")[0]
                if key and key not in keys:
                    problems.append({
                        "file": rel, "line": lineno, "kind": "undefined-key",
                        "attribute": attr, "target": val, "severity": "error",
                        "detail": "%s uses key '%s', which is not defined in any map. "
                                  "Reused content will be silently missing."
                                  % (attr, key)})

            for m in re.finditer(r'\bimage[^>]*?\bhref\s*=\s*"([^"]+)"', line):
                href = m.group(1).split("#")[0]
                if href.startswith(("http://", "https://")):
                    continue
                if href and not os.path.exists(os.path.normpath(os.path.join(base, href))):
                    problems.append({"file": rel, "line": lineno, "kind": "missing-image",
                                     "target": href, "severity": "error",
                                     "detail": "image %s does not exist" % href})
    return problems


def orphans(root):
    """Topics no map references. Either dead weight, or content that never got published -
    both worth knowing about."""
    referenced = set()
    for m in find_maps(root):
        base = os.path.dirname(os.path.abspath(m))
        for href in re.findall(r'href\s*=\s*"([^"]+)"', read_text(m)):
            h = href.split("#")[0]
            if h and not h.startswith(("http://", "https://")):
                referenced.add(os.path.normpath(os.path.join(base, h)))
    out = []
    for t in find_topics(root):
        if os.path.abspath(t) not in referenced:
            out.append({"file": os.path.relpath(t, root), "title": topic_title(t),
                        "type": topic_type(t)})
    return out


# ----------------------------------------------------------------------------------------
# statistics
# ----------------------------------------------------------------------------------------


def stats(root):
    maps = find_maps(root)
    topics = find_topics(root)
    ditavals = find_files(root, (".ditaval",))
    types, conref, keyref = {}, 0, 0
    words = 0
    for t in topics:
        types[topic_type(t)] = types.get(topic_type(t), 0) + 1
        text = read_text(t)
        if re.search(r"\bcon(?:key)?ref\s*=", text):
            conref += 1
        if re.search(r"\b(?:con)?keyref\s*=", text):
            keyref += 1
        # Rough: strip tags, count words. Good enough for "how big is this?".
        words += len(re.sub(r"<[^>]+>", " ", text).split())
    return {
        "maps": len(maps), "topics": len(topics), "ditavals": len(ditavals),
        "root_maps": [os.path.relpath(m, root) for m in root_maps(root)],
        "topic_types": dict(sorted(types.items(), key=lambda kv: -kv[1])),
        "topics_using_conref": conref, "topics_using_keyref": keyref,
        "keys_defined": len(list_keys(root)), "approx_words": words,
        "orphan_topics": len(orphans(root)),
    }


# ----------------------------------------------------------------------------------------
# creating content
# ----------------------------------------------------------------------------------------

SKELETONS = {
    "topic": ('topic', 'Topic', """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="%(id)s">
  <title>%(title)s</title>
  <shortdesc></shortdesc>
  <body>
    <p></p>
  </body>
</topic>
"""),
    "task": ('task', 'Task', """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
<task id="%(id)s">
  <title>%(title)s</title>
  <shortdesc></shortdesc>
  <taskbody>
    <prereq></prereq>
    <steps>
      <step><cmd></cmd></step>
    </steps>
    <result></result>
  </taskbody>
</task>
"""),
    "concept": ('concept', 'Concept', """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="%(id)s">
  <title>%(title)s</title>
  <shortdesc></shortdesc>
  <conbody>
    <p></p>
  </conbody>
</concept>
"""),
    "reference": ('reference', 'Reference', """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="%(id)s">
  <title>%(title)s</title>
  <shortdesc></shortdesc>
  <refbody>
    <section></section>
  </refbody>
</reference>
"""),
}


def slugify(title):
    s = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()
    return s or "untitled"


def new_topic(root, kind, title, dest=None):
    """Create a topic of the right type, with a valid skeleton.

    Types are semantic in DITA, not cosmetic: a task must contain steps. Starting from the
    correct skeleton avoids the most common structural mistake.
    """
    if kind not in SKELETONS:
        return {"ok": False, "error": "unknown type %r. Choose from: %s"
                                      % (kind, ", ".join(sorted(SKELETONS)))}
    slug = slugify(title)
    tag, _, tpl = SKELETONS[kind]
    folder = dest or os.path.join(root, "topics")
    if not os.path.isabs(folder):
        folder = os.path.join(root, folder)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%s.dita" % slug)
    if os.path.exists(path):
        return {"ok": False, "error": "already exists: %s" % os.path.relpath(path, root)}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(tpl % {"id": slug, "title": title})
    rel = os.path.relpath(path, root)
    return {"ok": True, "file": rel, "type": kind,
            "next_step": "Add it to a map so it gets published:\n"
                         "  <topicref href=\"%s\"/>" % rel}


# ----------------------------------------------------------------------------------------
# build and validate, via the toolkit when available
# ----------------------------------------------------------------------------------------


def toolkit():
    """What is available for building. Reported honestly so callers can degrade."""
    dita = shutil.which("dita")
    # Every key is always present, even when the tool is missing. A consumer should not
    # have to guess which keys exist before reading them.
    info = {"dita": dita, "dita_version": None,
            "docker": shutil.which("docker") is not None,
            "xmllint": shutil.which("xmllint") is not None}
    if dita:
        try:
            out = subprocess.run([dita, "--version"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=60)
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)",
                          out.stdout.decode("utf-8", errors="replace"))
            info["dita_version"] = m.group(1) if m else None
        except (OSError, subprocess.TimeoutExpired):
            info["dita_version"] = None
    info["can_build"] = bool(dita) or info["docker"]
    return info


def _run(cmd, cwd, timeout=1800):
    try:
        proc = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")
    except FileNotFoundError:
        return 127, "command not found: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "timed out after %ss" % timeout
    except OSError as exc:
        return 1, str(exc)


DIAG = re.compile(r"\b(DOT[A-Z]+\d+[EWF])\b")


def validate(root, map_path=None, strict=True):
    """Validate with the toolkit, then always run the static check as well.

    Both are run deliberately. A zero exit code from the toolkit is not proof that
    references resolved - unresolved conrefs in the PDF stage produced no message at all
    until a 2023 fix - so the static check provides independent evidence.
    """
    result = {"static": check_links(root), "toolkit": None}
    tk = toolkit()
    result["toolkit_available"] = tk["can_build"]

    if tk.get("dita"):
        target = map_path or (root_maps(root)[0] if root_maps(root) else None)
        if target:
            cmd = ["dita", "validate", "--input=%s" % target]
            if strict:
                cmd.append("--processing-mode=strict")
            rc, out = _run(cmd, root)
            codes = {}
            for c in DIAG.findall(out):
                codes[c] = codes.get(c, 0) + 1
            result["toolkit"] = {
                "input": os.path.relpath(target, root), "exit_code": rc,
                "passed": rc == 0, "diagnostics": dict(sorted(codes.items())),
                "output_tail": out[-2000:],
            }
    errors = [p for p in result["static"] if p["severity"] == "error"]
    result["summary"] = {
        "static_errors": len(errors),
        "toolkit_passed": (result["toolkit"] or {}).get("passed"),
        # Both must be clean. Either one alone is insufficient evidence.
        "ok": len(errors) == 0 and (result["toolkit"] or {}).get("passed", True),
    }
    return result


def build(root, deliverable=None):
    """Build through the project's own script, so this matches exactly what CI runs."""
    script = os.path.join(root, "scripts", "build.sh")
    if os.path.isfile(script):
        cmd = [script] + ([deliverable] if deliverable else [])
        rc, out = _run(cmd, root)
        return {"via": "scripts/build.sh", "exit_code": rc, "ok": rc == 0,
                "output_tail": out[-3000:]}

    project = os.path.join(root, "config", "dita-ot-project.xml")
    if os.path.isfile(project) and shutil.which("dita"):
        cmd = ["dita", "--project=config/dita-ot-project.xml", "--output=out"]
        if deliverable:
            cmd.append("--deliverable=%s" % deliverable)
        rc, out = _run(cmd, root)
        return {"via": "dita --project", "exit_code": rc, "ok": rc == 0,
                "output_tail": out[-3000:]}

    return {"ok": False, "error":
            "No build available. Expected scripts/build.sh or config/dita-ot-project.xml. "
            "Run `dac setup` to create them."}


def deliverables(root):
    project = os.path.join(root, "config", "dita-ot-project.xml")
    if not os.path.isfile(project):
        return []
    el, err = parse(project)
    if el is None:
        return []
    out = []
    for d in el.iter():
        if d.tag.split("}")[-1] == "deliverable":
            entry = {"id": d.get("id"), "name": d.get("name")}
            for child in d.iter():
                t = child.tag.split("}")[-1]
                if t == "publication" and child.get("transtype"):
                    entry["transtype"] = child.get("transtype")
                if t == "ditaval" and child.get("href"):
                    entry.setdefault("filters", []).append(child.get("href"))
                if t == "output" and child.get("href"):
                    entry["output"] = child.get("href")
            # A deliverable with no filter, in a repo that has ditavals, is the
            # green-and-wrong hazard waiting to happen.
            if not entry.get("filters") and find_files(root, (".ditaval",)):
                entry["warning"] = (
                    "No conditional filter declared, but this repository has .ditaval "
                    "files. A build without a filter publishes the wrong content and "
                    "still succeeds.")
            out.append(entry)
    return out


def context(root):
    """A compact picture of the repository, for an agent's prompt.

    Kept small on purpose: an agent that has to read a thousand files to answer a question
    will run out of room before it answers.
    """
    s = stats(root)
    return {
        "core_version": CORE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": os.path.abspath(root),
        "stats": s,
        "deliverables": deliverables(root),
        "toolkit": toolkit(),
        "root_maps": s["root_maps"],
        "link_problems": len([p for p in check_links(root) if p["severity"] == "error"]),
    }
