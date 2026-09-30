#!/usr/bin/env python3
"""Install the three interaction surfaces into a documentation repository.

Implements recipes R21, R22 and R23. This is real code rather than instructions, so the
result is identical every time and can be regression-tested.

    interfaces.py --root /path/to/docs              CLI + MCP server (the default)
    interfaces.py --root /path/to/docs --all        also the HTTP API
    interfaces.py --root /path/to/docs --dry-run    show what would change

Idempotent, and it merges rather than clobbers: an existing MCP configuration gains an
entry instead of being overwritten, because a writer may already have servers registered
that have nothing to do with DITA.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import shutil
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IFACE = os.path.join(os.path.dirname(HERE), "templates", "interfaces")

# source in templates/interfaces -> destination in the target repository
FILES = {
    "core": ("ditacore.py", os.path.join("scripts", "ditacore.py"), False),
    "cli": ("docs-cli.py", os.path.join("scripts", "docs"), True),
    "mcp": ("mcp-server.py", os.path.join("scripts", "mcp-server.py"), True),
    "api": ("api-server.py", os.path.join("scripts", "docs-api.py"), True),
}

# Each IDE, its config file, and the key its server map lives under.
IDE_CONFIGS = {
    "cursor": (os.path.join(".cursor", "mcp.json"), "mcpServers", "${workspaceFolder}"),
    "claude": (".mcp.json", "mcpServers", "."),
    "vscode": (os.path.join(".vscode", "mcp.json"), "servers", "${workspaceFolder}"),
}

SERVER_KEY = "dita-docs"


def detect_ides(root):
    """Which IDEs this repository or machine shows signs of.

    Configuring an editor nobody uses is harmless but confusing, so prefer evidence. When
    there is none, write the Cursor and Claude Code configurations, since those are the two
    DAC is invoked from.
    """
    found = []
    if os.path.isdir(os.path.join(root, ".cursor")) or os.path.isdir(
            os.path.expanduser("~/.cursor")):
        found.append("cursor")
    if os.path.isfile(os.path.join(root, ".mcp.json")) or os.path.isdir(
            os.path.expanduser("~/.claude")):
        found.append("claude")
    if os.path.isdir(os.path.join(root, ".vscode")):
        found.append("vscode")
    return found or ["cursor", "claude"]


def copy(src_name, dest_rel, executable, root, dry_run, actions):
    src = os.path.join(IFACE, src_name)
    if not os.path.isfile(src):
        actions.append({"action": "error", "detail": "missing template: %s" % src})
        return False
    dest = os.path.join(root, dest_rel)

    verb = "create"
    if os.path.isfile(dest):
        with open(src, "rb") as a, open(dest, "rb") as b:
            if a.read() == b.read():
                actions.append({"action": "unchanged", "path": dest_rel})
                return True
        verb = "update"

    if not dry_run:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        if executable:
            os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP
                     | stat.S_IXOTH)
    actions.append({"action": verb, "path": dest_rel,
                    "executable": executable})
    return True


def write_ide_config(ide, root, dry_run, actions):
    rel, server_key, workspace = IDE_CONFIGS[ide]
    path = os.path.join(root, rel)

    entry = {
        "command": "python3",
        "args": ["scripts/mcp-server.py"],
        "env": {"DITA_WORKSPACE": workspace},
    }
    if ide == "vscode":
        entry = dict(entry, type="stdio")

    existing = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except ValueError:
            actions.append({
                "action": "skipped", "path": rel,
                "detail": "already exists but is not valid JSON, so it was left alone. "
                          "Add the entry by hand - see templates/interfaces/mcp-config.md"})
            return

    servers = existing.get(server_key) or {}
    if servers.get(SERVER_KEY) == entry:
        actions.append({"action": "unchanged", "path": rel})
        return

    verb = "update" if os.path.isfile(path) else "create"
    others = [k for k in servers if k != SERVER_KEY]

    # Merge, never replace. Other servers in here are none of our business.
    servers[SERVER_KEY] = entry
    existing[server_key] = servers

    if not dry_run:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(existing, indent=2) + "\n")

    act = {"action": verb, "path": rel, "ide": ide}
    if others:
        act["preserved_servers"] = others
    actions.append(act)


def gitignore_state(root, dry_run, actions):
    """Keep credentials and build output out of version control.

    .dac/ can hold API tokens, so this is a safety step rather than tidiness.
    """
    path = os.path.join(root, ".gitignore")
    wanted = [".dac/state/", ".dac/journal.jsonl", "out/", "temp/"]
    current = ""
    if os.path.isfile(path):
        current = open(path, encoding="utf-8").read()
    missing = [w for w in wanted if w not in current]
    if not missing:
        actions.append({"action": "unchanged", "path": ".gitignore"})
        return
    if not dry_run:
        with open(path, "a", encoding="utf-8") as fh:
            if current and not current.endswith("\n"):
                fh.write("\n")
            fh.write("\n# Added by the DITA-as-Code Kit. .dac/ can contain API tokens.\n")
            for w in missing:
                fh.write(w + "\n")
    actions.append({"action": "update" if current else "create", "path": ".gitignore",
                    "added": missing})


def run(root, want_cli=True, want_mcp=True, want_api=False, ides=None, dry_run=False):
    root = os.path.abspath(root)
    actions = []

    # The shared engine is required by all three surfaces.
    copy(*FILES["core"], root=root, dry_run=dry_run, actions=actions)
    if want_cli:
        copy(*FILES["cli"], root=root, dry_run=dry_run, actions=actions)
    if want_mcp:
        copy(*FILES["mcp"], root=root, dry_run=dry_run, actions=actions)
        for ide in (ides or detect_ides(root)):
            if ide in IDE_CONFIGS:
                write_ide_config(ide, root, dry_run, actions)
    if want_api:
        copy(*FILES["api"], root=root, dry_run=dry_run, actions=actions)

    gitignore_state(root, dry_run, actions)

    return {
        "root": root, "dry_run": dry_run, "actions": actions,
        "installed": {"cli": want_cli, "mcp": want_mcp, "api": want_api},
        "verify": [
            "./scripts/docs stats" if want_cli else None,
            ("echo '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}' "
             "| python3 scripts/mcp-server.py") if want_mcp else None,
            "python3 scripts/docs-api.py --port 8765" if want_api else None,
        ],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Install the docs CLI, MCP server and HTTP API into a repository")
    ap.add_argument("--root", default=".", help="the documentation repository")
    ap.add_argument("--all", action="store_true", help="include the optional HTTP API")
    ap.add_argument("--no-cli", action="store_true")
    ap.add_argument("--no-mcp", action="store_true")
    ap.add_argument("--api", action="store_true", help="include the HTTP API")
    ap.add_argument("--ide", action="append",
                    choices=sorted(IDE_CONFIGS) + ["auto"], default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would change, without changing it")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isdir(args.root):
        print("error: not a directory: %s" % args.root, file=sys.stderr)
        return 2

    ides = None
    if args.ide and "auto" not in args.ide:
        ides = args.ide

    result = run(args.root, want_cli=not args.no_cli, want_mcp=not args.no_mcp,
                 want_api=args.all or args.api, ides=ides, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    if args.dry_run:
        print("Dry run. Nothing was changed.")
        print("")
    for a in result["actions"]:
        if a["action"] == "error":
            print("  error     %s" % a["detail"], file=sys.stderr)
        elif a["action"] == "unchanged":
            print("  unchanged %s" % a["path"])
        elif a["action"] == "skipped":
            print("  skipped   %s" % a["path"])
            print("            %s" % a["detail"])
        else:
            extra = ""
            if a.get("preserved_servers"):
                extra = "  (kept: %s)" % ", ".join(a["preserved_servers"])
            if a.get("added"):
                extra = "  (+%s)" % ", ".join(a["added"])
            print("  %-9s %s%s" % (a["action"], a["path"], extra))

    if any(a["action"] == "error" for a in result["actions"]):
        return 1

    print("")
    if result["installed"]["mcp"]:
        print("Restart your editor so it picks up the MCP server.")
        print("")
    print("Verify:")
    for cmd in [c for c in result["verify"] if c]:
        print("  %s" % cmd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
