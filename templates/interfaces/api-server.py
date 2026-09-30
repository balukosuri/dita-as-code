#!/usr/bin/env python3
"""A small HTTP API over your DITA documentation.

Installed by DAC into your repository. The same operations as the `docs` command and the
MCP server, as JSON over HTTP, for the cases where neither of those fits:

  - a dashboard showing documentation health
  - a CI job that posts the state of the docs somewhere
  - a script in a language that is not Python
  - a colleague who wants the numbers without installing anything

    python3 scripts/docs-api.py --port 8765
    curl localhost:8765/overview
    curl localhost:8765/check
    curl "localhost:8765/keys/product-name"

Deliberately constrained, because a documentation repository is not a web application:

  - **Binds to localhost only** unless you pass --host explicitly.
  - **Read-only.** No endpoint writes, builds or publishes anything. The CLI and MCP server
    can create a topic; this cannot.
  - **Single-threaded.** It is a local convenience, not a service. Do not put it behind a
    public address.

Standard library only.
"""

import argparse
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ditacore as core  # noqa: E402

API_VERSION = "0.1.0"
ROOT = os.getcwd()

INDEX = {
    "api_version": API_VERSION,
    "read_only": True,
    "endpoints": {
        "GET /": "this index",
        "GET /overview": "compact summary: counts, deliverables, toolkit, problem count",
        "GET /stats": "detailed counts by topic type, reuse usage, word estimate",
        "GET /check": "broken references, undefined keys, missing images",
        "GET /validate": "static check plus DITA-OT validation where available",
        "GET /structure": "the entry-point map resolved into a tree",
        "GET /structure?map=<path>": "a specific map resolved into a tree",
        "GET /keys": "every key defined, and where",
        "GET /keys/<key>": "one key explained, with its usages",
        "GET /uses/<key-or-path>": "what references this",
        "GET /orphans": "topics no map references",
        "GET /deliverables": "what this repository publishes",
        "GET /maps": "every map file",
        "GET /topics": "every topic file, with title and type",
        "GET /health": "liveness, for a monitor",
    },
    "notes": [
        "Read-only by design. Building and creating content are available through the "
        "`docs` command and the MCP server, not here.",
        "Bound to localhost unless --host was passed. Do not expose this publicly.",
    ],
}


class Handler(BaseHTTPRequestHandler):
    server_version = "dita-docs-api/%s" % API_VERSION

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, payload):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # A dashboard served from elsewhere on localhost is the main consumer.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {}
        if parsed.query:
            for part in parsed.query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    query[k] = unquote(v)

        try:
            status, payload = self.route(path, query)
        except ValueError as exc:
            status, payload = 400, {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - never take the server down
            status, payload = 500, {"error": "%s: %s" % (type(exc).__name__, exc)}
        self._send(status, payload)

    def do_POST(self):  # noqa: N802
        self._send(405, {"error": "This API is read-only.",
                         "hint": "Use the `docs` command or the MCP server to create "
                                 "content or build output."})

    # -- routing ------------------------------------------------------------------------

    def route(self, path, query):
        if path == "/":
            return 200, INDEX
        if path == "/health":
            return 200, {"ok": True, "root": ROOT, "api_version": API_VERSION}
        if path == "/overview":
            return 200, core.context(ROOT)
        if path == "/stats":
            return 200, core.stats(ROOT)

        if path == "/check":
            problems = core.check_links(ROOT)
            if query.get("severity", "error") == "error":
                problems = [p for p in problems if p["severity"] == "error"]
            by_kind = {}
            for p in problems:
                by_kind[p["kind"]] = by_kind.get(p["kind"], 0) + 1
            return 200, {"count": len(problems), "by_kind": by_kind, "problems": problems}

        if path == "/validate":
            m = self._safe(query["map"]) if query.get("map") else None
            strict = query.get("strict", "true").lower() != "false"
            return 200, core.validate(ROOT, m, strict=strict)

        if path == "/structure":
            target = self._safe(query["map"]) if query.get("map") else None
            if target is None:
                roots = core.root_maps(ROOT)
                if not roots:
                    return 404, {"error": "no maps found in this repository"}
                target = roots[0]
            return 200, core.map_tree(target, ROOT)

        if path == "/keys":
            keys = core.list_keys(ROOT)
            return 200, {"count": len(keys), "keys": keys}

        m = re.match(r"^/keys/(.+)$", path)
        if m:
            key = unquote(m.group(1))
            data = core.resolve_key(ROOT, key)
            return (200 if data["defined"] else 404), data

        m = re.match(r"^/uses/(.+)$", path)
        if m:
            target = unquote(m.group(1))
            if os.path.exists(os.path.join(ROOT, target)):
                self._safe(target)
                return 200, {"target": target, "kind": "file",
                             "usages": core.find_file_usages(ROOT, target)}
            return 200, {"target": target, "kind": "key",
                         "usages": core.find_key_usages(ROOT, target)}

        if path == "/orphans":
            o = core.orphans(ROOT)
            return 200, {"count": len(o), "orphans": o}
        if path == "/deliverables":
            return 200, {"deliverables": core.deliverables(ROOT)}
        if path == "/maps":
            maps = [os.path.relpath(p, ROOT) for p in core.find_maps(ROOT)]
            return 200, {"count": len(maps), "maps": maps,
                         "root_maps": [os.path.relpath(p, ROOT)
                                       for p in core.root_maps(ROOT)]}
        if path == "/topics":
            out = [{"file": os.path.relpath(p, ROOT), "title": core.topic_title(p),
                    "type": core.topic_type(p)} for p in core.find_topics(ROOT)]
            return 200, {"count": len(out), "topics": out}

        return 404, {"error": "no such endpoint: %s" % path,
                     "hint": "GET / lists what is available"}

    def _safe(self, rel):
        """Confine a query parameter to the repository."""
        candidate = os.path.realpath(os.path.join(ROOT, rel))
        if candidate != ROOT and not candidate.startswith(ROOT + os.sep):
            raise ValueError("path escapes the repository: %r" % rel)
        return candidate


def main(argv=None):
    global ROOT
    ap = argparse.ArgumentParser(description="Read-only HTTP API over your DITA docs")
    ap.add_argument("--root", default=".", help="repository root")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1",
                    help="bind address. Defaults to localhost; change it deliberately.")
    ap.add_argument("--verbose", action="store_true", help="log each request")
    args = ap.parse_args(argv)

    # realpath, not abspath, so the confinement check below can match. See the same
    # note in mcp-server.py: on macOS /var and /tmp are symlinks into /private.
    ROOT = os.path.realpath(args.root)
    if not os.path.isdir(ROOT):
        print("error: not a directory: %s" % ROOT, file=sys.stderr)
        return 2

    server = HTTPServer((args.host, args.port), Handler)
    server.verbose = args.verbose

    s = core.stats(ROOT)
    print("Serving %d maps and %d topics from %s" % (s["maps"], s["topics"], ROOT))
    print("  http://%s:%d/" % (args.host, args.port))
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print("")
        print("  WARNING: bound to %s rather than localhost. This API has no "
              "authentication." % args.host)
    print("")
    print("  Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
