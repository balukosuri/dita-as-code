#!/usr/bin/env python3
"""MCP server for your DITA documentation.

Installed by DAC into your repository. Lets Cursor, Claude Code or Copilot work with your
DITA directly instead of guessing from file contents, so you can ask things like:

    "Is anything broken in the docs?"
    "What would break if I rename install-overview.dita?"
    "Show me the structure of the user guide"
    "Create a task topic called Configuring TLS"
    "Which topics use the key product-name?"

Speaks the Model Context Protocol over stdio: JSON-RPC 2.0, newline-delimited. Implemented
against the standard library alone, so there is nothing to install and nothing to keep in
step with an SDK release cycle.

Register it with your AI IDE - DAC writes the configuration for you. To check it by hand:

    echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 mcp-server.py

Safety: read-mostly. Exactly one tool writes anything, and it can only create a new topic
file. Nothing deletes, nothing publishes, and every path is confined to the workspace root.
"""

import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ditacore as core  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "dita-docs"
SERVER_VERSION = "0.1.0"

# The workspace this server is allowed to touch. Set by DAC in the generated config.
#
# realpath, not abspath: the confinement check below resolves symlinks, so the root must be
# resolved the same way or the two can never match. On macOS /var and /tmp are symlinks
# into /private, which made every legitimate relative path look like an escape attempt.
ROOT = os.path.realpath(os.environ.get("DITA_WORKSPACE") or os.getcwd())


def safe_path(rel):
    """Confine a caller-supplied path to the workspace.

    An agent will occasionally pass something surprising, so absolute paths, traversal and
    symlink escapes are all rejected rather than trusted.
    """
    if not rel:
        return None
    if "\x00" in rel:
        raise ValueError("path contains a null byte")
    candidate = os.path.realpath(os.path.join(ROOT, rel))
    if candidate != ROOT and not candidate.startswith(ROOT + os.sep):
        raise ValueError("path escapes the workspace: %r" % rel)
    return candidate


# ----------------------------------------------------------------------------------------
# tools
# ----------------------------------------------------------------------------------------

TOOLS = [
    {
        "name": "dita_overview",
        "description": (
            "Summarise this DITA documentation: how many maps and topics, which topic "
            "types, how much content reuse, what it publishes, and whether anything is "
            "broken. Call this first when you need orientation - it is deliberately "
            "compact so it fits in a prompt."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dita_check_references",
        "description": (
            "Find broken references: missing files, undefined keys, missing images and "
            "malformed XML. Runs statically, so it needs no Java and no toolkit. An "
            "undefined key is serious - it means reused content is silently missing from "
            "the published page and nothing warns you at build time."),
        "inputSchema": {"type": "object", "properties": {
            "severity": {"type": "string", "enum": ["error", "all"],
                         "description": "default error"}}},
    },
    {
        "name": "dita_map_structure",
        "description": (
            "Resolve a DITA map into its full tree, following mapref and topicref, with "
            "titles and topic types. Marks missing targets and circular references. Omit "
            "the map to use the entry point."),
        "inputSchema": {"type": "object", "properties": {
            "map": {"type": "string", "description": "path relative to the repository root"},
            "max_depth": {"type": "integer", "description": "trim the tree for brevity"}}},
    },
    {
        "name": "dita_resolve_key",
        "description": (
            "Explain a key: where it is defined, what it points at, whether that target "
            "exists, and every place it is used. Also reports a key defined more than "
            "once, where the winner depends on map order."),
        "inputSchema": {"type": "object",
                        "properties": {"key": {"type": "string"}},
                        "required": ["key"]},
    },
    {
        "name": "dita_list_keys",
        "description": "Every key defined in this documentation, and which map defines it.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dita_find_usages",
        "description": (
            "What references a key or a file. ALWAYS call this before suggesting a rename, "
            "move or delete: renaming a DITA file breaks every reference to it with no "
            "warning at edit time."),
        "inputSchema": {"type": "object", "properties": {
            "target": {"type": "string", "description": "a key name or a file path"}},
            "required": ["target"]},
    },
    {
        "name": "dita_orphans",
        "description": ("Topics that no map references, so they are not published. Either "
                        "content that was forgotten, or content that should be deleted."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dita_validate",
        "description": (
            "Validate the documentation. Runs the static reference check always, plus "
            "DITA-OT validation when a toolkit is available. Both are reported, because a "
            "passing build is NOT evidence that references resolved."),
        "inputSchema": {"type": "object", "properties": {
            "map": {"type": "string"},
            "strict": {"type": "boolean", "description": "default true"}}},
    },
    {
        "name": "dita_deliverables",
        "description": (
            "What this repository publishes: each deliverable, its output format and its "
            "conditional filter. Warns about a deliverable with no filter in a repository "
            "that has them, because such a build publishes the wrong content and still "
            "succeeds."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "dita_build",
        "description": (
            "Build documentation output through the repository's own build script, so the "
            "result matches exactly what CI produces. Can take a while on a large estate."),
        "inputSchema": {"type": "object", "properties": {
            "deliverable": {"type": "string",
                            "description": "which one; omit to build everything"}}},
    },
    {
        "name": "dita_read_topic",
        "description": "Read one DITA file, with its resolved title and topic type.",
        "inputSchema": {"type": "object",
                        "properties": {"path": {"type": "string"}},
                        "required": ["path"]},
    },
    {
        "name": "dita_new_topic",
        "description": (
            "Create a new topic with a valid skeleton for its type. THE ONLY TOOL HERE "
            "THAT WRITES ANYTHING, and it can only create a file that does not yet exist. "
            "Choose the type deliberately: types are semantic in DITA, so a task must "
            "contain steps and validation enforces it."),
        "inputSchema": {"type": "object", "properties": {
            "type": {"type": "string", "enum": ["topic", "task", "concept", "reference"]},
            "title": {"type": "string"},
            "dest": {"type": "string", "description": "folder; default topics/"}},
            "required": ["type", "title"]},
    },
]

RESOURCES = [
    {"uri": "dita://overview", "name": "Documentation overview",
     "description": "Compact summary of this DITA estate", "mimeType": "application/json"},
    {"uri": "dita://diagnostics", "name": "Reference problems",
     "description": "Broken links and undefined keys", "mimeType": "application/json"},
    {"uri": "dita://keys", "name": "Keys",
     "description": "Every key defined, and where", "mimeType": "application/json"},
    {"uri": "dita://structure", "name": "Map structure",
     "description": "The entry-point map resolved into a tree", "mimeType": "application/json"},
]


def _trim(node, depth, current=0):
    if depth is None or current >= depth:
        if node.get("children"):
            node = dict(node)
            node["children_omitted"] = len(node["children"])
            node["children"] = []
        return node
    if node.get("children"):
        node = dict(node)
        node["children"] = [_trim(c, depth, current + 1) for c in node["children"]]
    return node


def call_tool(name, args):
    args = args or {}

    if name == "dita_overview":
        return core.context(ROOT)

    if name == "dita_check_references":
        problems = core.check_links(ROOT)
        if args.get("severity", "error") == "error":
            problems = [p for p in problems if p["severity"] == "error"]
        by_kind = {}
        for p in problems:
            by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1
        return {"count": len(problems), "by_kind": by_kind, "problems": problems[:200],
                "truncated": len(problems) > 200}

    if name == "dita_map_structure":
        target = safe_path(args["map"]) if args.get("map") else None
        if target is None:
            roots = core.root_maps(ROOT)
            if not roots:
                return {"error": "no maps found in this workspace"}
            target = roots[0]
        tree = core.map_tree(target, ROOT)
        depth = args.get("max_depth")
        return _trim(tree, depth) if depth else tree

    if name == "dita_resolve_key":
        return core.resolve_key(ROOT, args["key"])

    if name == "dita_list_keys":
        keys = core.list_keys(ROOT)
        return {"count": len(keys), "keys": keys}

    if name == "dita_find_usages":
        target = args["target"]
        if os.path.exists(os.path.join(ROOT, target)):
            safe_path(target)
            return {"target": target, "kind": "file",
                    "usages": core.find_file_usages(ROOT, target),
                    "note": "Renaming or deleting this breaks every reference listed. Use "
                            "the editor's refactoring command, never mv."}
        return {"target": target, "kind": "key",
                "usages": core.find_key_usages(ROOT, target)}

    if name == "dita_orphans":
        o = core.orphans(ROOT)
        return {"count": len(o), "orphans": o}

    if name == "dita_validate":
        m = safe_path(args["map"]) if args.get("map") else None
        return core.validate(ROOT, m, strict=args.get("strict", True))

    if name == "dita_deliverables":
        return {"deliverables": core.deliverables(ROOT)}

    if name == "dita_build":
        return core.build(ROOT, args.get("deliverable"))

    if name == "dita_read_topic":
        p = safe_path(args["path"])
        if not p or not os.path.isfile(p):
            return {"error": "not found: %s" % args["path"]}
        return {"path": os.path.relpath(p, ROOT), "title": core.topic_title(p),
                "type": core.topic_type(p), "content": core.read_text(p)}

    if name == "dita_new_topic":
        dest = args.get("dest")
        if dest:
            safe_path(dest)
        return core.new_topic(ROOT, args["type"], args["title"], dest)

    return {"error": "unknown tool: %s" % name}


def read_resource(uri):
    if uri == "dita://overview":
        return core.context(ROOT)
    if uri == "dita://diagnostics":
        problems = core.check_links(ROOT)
        return {"count": len(problems), "problems": problems}
    if uri == "dita://keys":
        return core.list_keys(ROOT)
    if uri == "dita://structure":
        roots = core.root_maps(ROOT)
        if not roots:
            return {"error": "no maps found"}
        return core.map_tree(roots[0], ROOT)
    return {"error": "unknown resource: %s" % uri}


# ----------------------------------------------------------------------------------------
# JSON-RPC plumbing
# ----------------------------------------------------------------------------------------


def respond(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(msg):
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return respond(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}, "resources": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Tools for working with DITA documentation in this workspace. Start with "
                "dita_overview for orientation. Before suggesting any rename, move or "
                "delete, call dita_find_usages - renaming a DITA file breaks every "
                "reference to it with no warning at edit time. Remember that a passing "
                "build is not evidence that references resolved, so use dita_validate "
                "rather than inferring correctness from dita_build succeeding."),
        })

    # Notifications carry no id and expect no reply.
    if method in ("notifications/initialized", "initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return respond(msg_id, {})

    if method == "tools/list":
        return respond(msg_id, {"tools": TOOLS})

    if method == "resources/list":
        return respond(msg_id, {"resources": RESOURCES})

    if method == "resources/read":
        uri = params.get("uri", "")
        data = read_resource(uri)
        return respond(msg_id, {"contents": [{
            "uri": uri, "mimeType": "application/json",
            "text": json.dumps(data, indent=2)}]})

    if method == "tools/call":
        name = params.get("name")
        try:
            data = call_tool(name, params.get("arguments"))
        except ValueError as exc:
            return respond(msg_id, {
                "content": [{"type": "text", "text": "Rejected: %s" % exc}],
                "isError": True})
        except Exception as exc:  # noqa: BLE001 - a tool must not kill the server
            return respond(msg_id, {
                "content": [{"type": "text",
                             "text": "%s failed: %s\n%s" % (name, exc,
                                                            traceback.format_exc()[-800:])}],
                "isError": True})
        is_error = isinstance(data, dict) and "error" in data
        return respond(msg_id, {
            "content": [{"type": "text", "text": json.dumps(data, indent=2)}],
            "isError": bool(is_error)})

    if method and method.startswith("notifications/"):
        return None

    return error(msg_id, -32601, "method not found: %s" % method)


def main():
    if not os.path.isdir(ROOT):
        print("workspace does not exist: %s" % ROOT, file=sys.stderr)
        return 2
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps(error(None, -32700, "parse error")) + "\n")
            sys.stdout.flush()
            continue
        try:
            reply = handle(msg)
        except Exception as exc:  # noqa: BLE001
            reply = error(msg.get("id"), -32603, "internal error: %s" % exc)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
