#!/usr/bin/env python3
"""docs - a command line for your own documentation.

Installed by DAC into your repository. Every command works on your DITA without you
needing to know DITA-OT's arguments.

    docs stats                     how big is this, and what is in it
    docs tree                      the map structure, as a tree
    docs check                     find broken links and undefined keys
    docs validate                  full validation, using the toolkit if available
    docs build [deliverable]       build output
    docs deliverables              what this repository publishes
    docs keys [key]                list keys, or explain one
    docs uses <key-or-file>        what would break if you changed this
    docs orphans                   topics no map references
    docs new task "Some title"     create a topic of the right type
    docs context                   a compact summary, as JSON

Add --json to any command for machine-readable output.

Standard library only. Nothing to install.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ditacore as core  # noqa: E402


# ----------------------------------------------------------------------------------------
# output helpers
# ----------------------------------------------------------------------------------------

BOLD = "\033[1m" if sys.stdout.isatty() else ""
DIM = "\033[2m" if sys.stdout.isatty() else ""
RED = "\033[31m" if sys.stdout.isatty() else ""
GREEN = "\033[32m" if sys.stdout.isatty() else ""
YELLOW = "\033[33m" if sys.stdout.isatty() else ""
OFF = "\033[0m" if sys.stdout.isatty() else ""


def head(text):
    print("%s%s%s" % (BOLD, text, OFF))


def emit(data, as_json):
    if as_json:
        print(json.dumps(data, indent=2))
        return True
    return False


# ----------------------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------------------


def cmd_stats(args):
    s = core.stats(args.root)
    if emit(s, args.json):
        return 0
    head("Your documentation")
    print("")
    print("  %-26s %d" % ("Maps", s["maps"]))
    print("  %-26s %d" % ("Topics", s["topics"]))
    print("  %-26s %d" % ("Conditional filters", s["ditavals"]))
    print("  %-26s %d" % ("Keys defined", s["keys_defined"]))
    print("  %-26s ~%d" % ("Words", s["approx_words"]))
    print("")
    if s["topic_types"]:
        print("  By type:")
        for t, n in s["topic_types"].items():
            print("    %-24s %d" % (t, n))
        print("")
    print("  %-26s %d topic(s)" % ("Using conref", s["topics_using_conref"]))
    print("  %-26s %d topic(s)" % ("Using keyref", s["topics_using_keyref"]))
    if s["topics_using_conref"]:
        print("")
        print("  %sContent reuse is genuinely in use here.%s That is the main thing DITA"
              % (DIM, OFF))
        print("  %sdoes that lightweight formats cannot replicate.%s" % (DIM, OFF))
    if s["orphan_topics"]:
        print("")
        print("  %s%d topic(s) are not referenced by any map.%s Run: docs orphans"
              % (YELLOW, s["orphan_topics"], OFF))
    if s["root_maps"]:
        print("")
        print("  Entry points (maps nothing else references):")
        for m in s["root_maps"][:8]:
            print("    %s" % m)
    return 0


def _print_tree(children, prefix=""):
    for i, c in enumerate(children):
        last = i == len(children) - 1
        branch = "`-- " if last else "|-- "
        label = c.get("title") or c.get("navtitle") or c.get("href") or c.get("kind")
        mark = ""
        if c.get("href") and c.get("exists") is False:
            mark = " %s<-- MISSING%s" % (RED, OFF)
        if c.get("cycle"):
            mark = " %s<-- circular reference%s" % (RED, OFF)
        kind = c.get("type") or c.get("kind") or ""
        print("%s%s%s %s(%s)%s%s" % (prefix, branch, label, DIM, kind, OFF, mark))
        if c.get("children"):
            _print_tree(c["children"], prefix + ("    " if last else "|   "))


def cmd_tree(args):
    target = args.map
    if not target:
        roots = core.root_maps(args.root)
        if not roots:
            print("No maps found in %s" % args.root, file=sys.stderr)
            return 1
        target = roots[0]
        if len(roots) > 1 and not args.json:
            print("%sSeveral entry points exist; showing the first.%s" % (DIM, OFF))
            for r in roots:
                print("  %s" % os.path.relpath(r, args.root))
            print("")
    if not os.path.isabs(target):
        target = os.path.join(args.root, target)
    tree = core.map_tree(target, os.path.abspath(args.root))
    if emit(tree, args.json):
        return 0
    head(tree.get("title") or tree["path"])
    print("")
    _print_tree(tree.get("children", []))
    flat = core.flatten(tree)
    missing = [c for c in flat if c.get("exists") is False]
    print("")
    print("  %d entries, %d missing" % (len(flat), len(missing)))
    return 1 if missing else 0


def cmd_check(args):
    problems = core.check_links(args.root)
    if emit({"problems": problems, "count": len(problems)}, args.json):
        return 1 if problems else 0
    if not problems:
        head("%sNo broken references found.%s" % (GREEN, OFF))
        print("")
        print("  %sThis check does not need Java or the toolkit, so it is safe to run%s"
              % (DIM, OFF))
        print("  %sbefore you have installed anything. For full validation: docs validate%s"
              % (DIM, OFF))
        return 0
    head("%s%d problem(s) found%s" % (RED, len(problems), OFF))
    print("")
    by_kind = {}
    for p in problems:
        by_kind.setdefault(p["kind"], []).append(p)
    for kind, items in sorted(by_kind.items()):
        print("%s%s (%d)%s" % (BOLD, kind.replace("-", " "), len(items), OFF))
        for p in items[:args.limit]:
            print("  %s:%s" % (p["file"], p["line"]))
            print("      %s" % p["detail"])
        if len(items) > args.limit:
            print("  %s... and %d more%s" % (DIM, len(items) - args.limit, OFF))
        print("")
    if any(p["kind"] == "undefined-key" for p in problems):
        print("%sAn undefined key means reused content is silently missing from the%s"
              % (YELLOW, OFF))
        print("%spublished page. Nothing will warn you at build time.%s" % (YELLOW, OFF))
    return 1


def cmd_validate(args):
    result = core.validate(args.root, args.map, strict=not args.lenient)
    if emit(result, args.json):
        return 0 if result["summary"]["ok"] else 1
    head("Validation")
    print("")
    errs = [p for p in result["static"] if p["severity"] == "error"]
    print("  Static reference check : %s%d error(s)%s"
          % (RED if errs else GREEN, len(errs), OFF))
    tk = result.get("toolkit")
    if tk:
        print("  Toolkit validation     : %s%s%s (exit %d)"
              % (GREEN if tk["passed"] else RED,
                 "passed" if tk["passed"] else "FAILED", OFF, tk["exit_code"]))
        if tk["diagnostics"]:
            print("")
            print("  Diagnostics:")
            for code, n in tk["diagnostics"].items():
                print("    %-12s %d" % (code, n))
    elif not result["toolkit_available"]:
        print("  Toolkit validation     : %sskipped - no DITA-OT available%s" % (DIM, OFF))
        print("")
        print("  %sThe static check above still ran, so this is not a blind spot -%s"
              % (DIM, OFF))
        print("  %sjust a narrower one. Install Java 17 and DITA-OT for the rest.%s"
              % (DIM, OFF))
    print("")
    if result["summary"]["ok"]:
        print("%sEverything passed.%s" % (GREEN, OFF))
        return 0
    print("%sSomething failed. Run `docs check` for the detail on references.%s" % (RED, OFF))
    print("")
    print("%sNote: a passing build does NOT mean the content is correct. These are%s"
          % (DIM, OFF))
    print("%sdifferent questions, which is why both checks run.%s" % (DIM, OFF))
    return 1


def cmd_build(args):
    if not args.json:
        head("Building%s" % (" '%s'" % args.deliverable if args.deliverable else " everything"))
        print("")
    result = core.build(args.root, args.deliverable)
    if emit(result, args.json):
        return 0 if result.get("ok") else 1
    if not result.get("ok"):
        print("%sBuild failed.%s" % (RED, OFF))
        print("")
        print(result.get("error") or result.get("output_tail", "")[-1500:])
        return 1
    print(result.get("output_tail", "")[-800:])
    print("")
    print("%sBuild succeeded%s (via %s)." % (GREEN, OFF, result["via"]))
    print("")
    print("%sA successful build is not evidence the content is correct. Run%s" % (DIM, OFF))
    print("%s`docs validate` for that - they are genuinely different questions.%s" % (DIM, OFF))
    return 0


def cmd_deliverables(args):
    ds = core.deliverables(args.root)
    if emit(ds, args.json):
        return 0
    if not ds:
        print("No deliverables defined. Expected config/dita-ot-project.xml.")
        print("Run `dac setup` to create one.")
        return 1
    head("What this repository publishes")
    print("")
    for d in ds:
        print("  %s%-14s%s %s" % (BOLD, d.get("id") or "?", OFF, d.get("name") or ""))
        if d.get("transtype"):
            print("      format  %s" % d["transtype"])
        if d.get("output"):
            print("      output  %s" % d["output"])
        if d.get("filters"):
            print("      filter  %s" % ", ".join(d["filters"]))
        if d.get("warning"):
            print("      %s%s%s" % (YELLOW, d["warning"], OFF))
        print("")
    print("Build one with:  docs build <id>")
    return 0


def cmd_keys(args):
    if args.key:
        r = core.resolve_key(args.root, args.key)
        if emit(r, args.json):
            return 0 if r["defined"] else 1
        head("Key: %s" % args.key)
        print("")
        if not r["defined"]:
            print("%sNot defined in any map.%s" % (RED, OFF))
            print("")
            print("Any conkeyref or keyref using it resolves to nothing, which means")
            print("reused content is silently missing from published output.")
            return 1
        for d in r["definitions"]:
            print("  defined in %s:%s" % (d["map"], d["line"]))
            if d.get("href"):
                print("      -> %s" % d["href"])
        if r.get("warning"):
            print("")
            print("  %s%s%s" % (YELLOW, r["warning"], OFF))
        if r.get("target"):
            ok = r.get("target_exists")
            print("")
            print("  target %s %s" % (r["target"],
                                      "" if ok else "%s(MISSING)%s" % (RED, OFF)))
        print("")
        print("  used in %d place(s)" % len(r["used_in"]))
        for u in r["used_in"][:args.limit]:
            print("    %s:%s" % (u["file"], u["line"]))
        if len(r["used_in"]) > args.limit:
            print("    %s... and %d more%s" % (DIM, len(r["used_in"]) - args.limit, OFF))
        return 0

    keys = core.list_keys(args.root)
    if emit(keys, args.json):
        return 0
    head("%d key(s) defined" % len(keys))
    print("")
    for k in sorted(keys):
        defs = keys[k]
        dup = " %s(defined %dx)%s" % (YELLOW, len(defs), OFF) if len(defs) > 1 else ""
        print("  %-38s %s%s" % (k, defs[0]["map"], dup))
    print("")
    print("Explain one with:  docs keys <name>")
    return 0


def cmd_uses(args):
    target = args.target
    as_file = os.path.exists(os.path.join(args.root, target))
    if as_file:
        hits = core.find_file_usages(args.root, target)
        label = "file"
    else:
        hits = core.find_key_usages(args.root, target)
        label = "key"
    if emit({"target": target, "kind": label, "usages": hits}, args.json):
        return 0
    head("References to %s '%s'" % (label, target))
    print("")
    if not hits:
        print("  Nothing references it.")
        if label == "file":
            print("")
            print("  %sSafe to move or delete, as far as references go.%s" % (DIM, OFF))
        return 0
    for h in hits[:args.limit]:
        extra = h.get("attribute") or ""
        print("  %s:%s  %s" % (h["file"], h["line"], extra))
    if len(hits) > args.limit:
        print("  %s... and %d more%s" % (DIM, len(hits) - args.limit, OFF))
    print("")
    print("%s%d reference(s). Renaming or deleting breaks every one of them, with no%s"
          % (YELLOW, len(hits), OFF))
    print("%swarning at edit time. Use your editor's refactoring command instead of mv.%s"
          % (YELLOW, OFF))
    return 0


def cmd_orphans(args):
    o = core.orphans(args.root)
    if emit({"orphans": o, "count": len(o)}, args.json):
        return 0
    if not o:
        head("%sEvery topic is referenced by a map.%s" % (GREEN, OFF))
        return 0
    head("%d topic(s) not referenced by any map" % len(o))
    print("")
    for t in o[:args.limit]:
        print("  %-52s %s%s%s" % (t["file"], DIM, t["type"], OFF))
    if len(o) > args.limit:
        print("  %s... and %d more%s" % (DIM, len(o) - args.limit, OFF))
    print("")
    print("These are not published. Either add them to a map, or delete them.")
    return 0


def cmd_new(args):
    r = core.new_topic(args.root, args.type, args.title, args.dest)
    if emit(r, args.json):
        return 0 if r["ok"] else 1
    if not r["ok"]:
        print("%s%s%s" % (RED, r["error"], OFF))
        return 1
    head("Created %s" % r["file"])
    print("")
    print(r["next_step"])
    print("")
    print("%sThe skeleton matches the topic type, because types are semantic in DITA:%s"
          % (DIM, OFF))
    print("%sa task must contain steps, and validation enforces that.%s" % (DIM, OFF))
    return 0


def cmd_context(args):
    print(json.dumps(core.context(args.root), indent=2))
    return 0


# ----------------------------------------------------------------------------------------


def main(argv=None):
    # The common flags are attached to a parent parser AND to every subcommand, so
    # `docs check --limit 3` works as naturally as `docs --limit 3 check`. Putting a flag
    # after the subcommand is what people actually type.
    # The global flags are pulled out of the argument list first, wherever they appear, so
    # that both `docs --root X stats` and `docs stats --root X` work. The obvious approach
    # - attaching them to every subparser via parents= - does not work: argparse copies the
    # subparser's namespace over the parent's afterwards, so a value given before the
    # subcommand is silently replaced by the subcommand's default. That bug made
    # `--root` appear to be accepted while the wrong directory was scanned.
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--root", default=".",
                     help="repository root (default: current directory)")
    pre.add_argument("--json", action="store_true", help="machine-readable output")
    pre.add_argument("--limit", type=int, default=20, help="how many items to list")
    globals_ns, remaining = pre.parse_known_args(
        list(sys.argv[1:] if argv is None else argv))

    ap = argparse.ArgumentParser(
        prog="docs", parents=[pre],
        description="Work with your DITA documentation from the command line")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, helptext, fn):
        p = sub.add_parser(name, help=helptext)
        p.set_defaults(func=fn)
        return p

    add("stats", "how big is this, and what is in it", cmd_stats)

    p = add("tree", "the map structure, as a tree", cmd_tree)
    p.add_argument("map", nargs="?", help="which map (default: the entry point)")

    add("check", "find broken links and undefined keys", cmd_check)

    p = add("validate", "full validation, using the toolkit if available", cmd_validate)
    p.add_argument("map", nargs="?")
    p.add_argument("--lenient", action="store_true",
                   help="do not use strict processing mode")

    p = add("build", "build output", cmd_build)
    p.add_argument("deliverable", nargs="?")

    add("deliverables", "what this repository publishes", cmd_deliverables)

    p = add("keys", "list keys, or explain one", cmd_keys)
    p.add_argument("key", nargs="?")

    p = add("uses", "what would break if you changed this", cmd_uses)
    p.add_argument("target", help="a key name or a file path")

    add("orphans", "topics no map references", cmd_orphans)

    p = add("new", "create a topic of the right type", cmd_new)
    p.add_argument("type", choices=sorted(core.SKELETONS))
    p.add_argument("title")
    p.add_argument("--dest", help="folder to create it in (default: topics/)")

    add("context", "a compact summary, as JSON", cmd_context)

    args = ap.parse_args(remaining)
    # Re-apply the globals, which were consumed before the subcommand was parsed.
    args.root, args.json, args.limit = globals_ns.root, globals_ns.json, globals_ns.limit
    if not os.path.isdir(args.root):
        print("error: not a directory: %s" % args.root, file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
