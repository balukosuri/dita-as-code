# 7. Your toolkit: CLI, MCP and API

The three ways to work with your DITA after setup. Install them, configure them, use them.

This is the part that makes DITA-as-code liveable day to day. A pipeline that builds your docs but
cannot answer a question about them is a pipeline you will not trust.

---

## Installing them

```bash
dac interfaces                    # the CLI and MCP server
dac interfaces --all              # also the HTTP API
dac interfaces --dry-run          # show what would change, change nothing
```

You get:

```
scripts/ditacore.py       the shared engine
scripts/docs              a command line          (executable)
scripts/mcp-server.py     typed tools for your AI IDE
scripts/docs-api.py       read-only HTTP API      (--all only)
.cursor/mcp.json          MCP registration        (whichever IDE was detected)
.gitignore                updated to protect .dac/
```

Three things it does deliberately:

- **Merges, never clobbers.** An existing MCP configuration gains a `dita-docs` entry; servers you
  already had are preserved.
- **Idempotent.** Running it twice reports `unchanged` and rewrites nothing.
- **Refuses to touch invalid JSON.** If your `mcp.json` is malformed it says so and leaves the
  file alone rather than replacing it.

Nothing to install beyond this. All three are Python standard library only, so there is no
`pip install` and no lockfile.

---

## The `docs` command

```bash
./scripts/docs stats
```

Put `scripts/` on your `PATH`, or alias it, and it becomes just `docs`.

### Every command

| Command | What it answers |
|---|---|
| `docs stats` | How big is this, what is in it, how much reuse |
| `docs tree [map]` | The map structure, with missing targets marked |
| `docs check` | What is broken — **no Java required** |
| `docs validate [map]` | Full validation, using the toolkit when available |
| `docs build [deliverable]` | Build output, through the same script CI runs |
| `docs deliverables` | What this repository publishes, and with which filters |
| `docs keys [key]` | List keys, or explain one |
| `docs uses <key-or-file>` | What breaks if you change this |
| `docs orphans` | Topics no map references |
| `docs new <type> "Title"` | Create a topic with the right skeleton |
| `docs context` | A compact JSON summary |

Add `--json` to any of them for machine-readable output. `--root` works before or after the
subcommand. `--limit` controls how many items are listed.

### The four worth knowing

**`docs check` — the one to run before you push.** It resolves every reference statically, so it
needs no toolkit and no Java. That means it works on day one, before you have installed anything.

```
513 problem(s) found

missing image (211)
  content/n1ql/images/alterindex_CONFLICTED.xml:53
      image images/alter-index-clause.png does not exist

undefined key (1)
  content/sdk/c/managing-connections.dita:169
      keyref uses key 'client-settings', which is not defined in any map.
      Reused content will be silently missing.
```

That is real output from Couchbase Server's published documentation. An undefined key is the
serious one: reused content vanishes from the published page and **nothing warns you at build
time**.

**`docs uses` — run this before any rename.** Renaming a DITA file breaks every reference to it
with no warning at edit time. This tells you the cost first.

```
$ docs uses content/sdk/c/managing-connections.dita
  content/sdk/nodejs/managing-connections.dita:61  conref
  content/sdk/php/managing-connections.dita:83     conref
  ...
5 reference(s). Renaming or deleting breaks every one of them.
```

**`docs keys <key>` — for when a conkeyref will not resolve.** It finds the cause, which the
toolkit's error message usually does not give you:

```
$ docs keys lcb-ssl-preamble
  defined in content/sdk/c.ditamap:13      -> c/lcb-pars-shared.dita#toplevel
  defined in content/sdk/nodejs.ditamap:5  -> nodejs/nodejs-shared-pars.dita#toplevel

  Defined 2 times. Which one wins depends on map order.
```

**`docs new` — because topic types are semantic.** A task must contain steps, and validation
enforces it. Starting from the right skeleton avoids the most common structural mistake.

---

## The MCP server

This is the surface that matters most for DITA, and it is worth understanding why.

**The questions writers actually have are graph questions.** Where is this key defined? What
references this file? Why will this conkeyref not resolve? The answers live in the *relationships
between* files, not inside any one file — so an AI assistant reading raw text cannot answer them
reliably, however good it is. The MCP server gives it the graph.

### Configuring it

`dac interfaces` writes the configuration for the IDE it detects. To do it by hand, see
[`templates/interfaces/mcp-config.md`](../templates/interfaces/mcp-config.md). The short version:

**Cursor** — `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "dita-docs": {
      "command": "python3",
      "args": ["scripts/mcp-server.py"],
      "env": { "DITA_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```

**Claude Code** — the same content in `.mcp.json`, or `claude mcp add dita-docs -- python3 scripts/mcp-server.py`.

**VS Code with Copilot** — `.vscode/mcp.json`, with `"type": "stdio"` added.

Restart your editor afterwards.

### Checking it works

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 scripts/mcp-server.py
```

You should get JSON listing twelve tools. If you get nothing, run it without the pipe and read the
error — usually `DITA_WORKSPACE` pointing somewhere that does not exist.

### What you can ask

> Is anything broken in the docs?

> What would break if I rename `install-overview.dita`?

> Show me the structure of the user guide.

> Why is this conkeyref not resolving?

> Which topics use the key `product-name`?

> Create a task topic called "Configuring TLS" in the security folder.

> Which topics are not in any map?

The second is the habit worth forming. The tool descriptions instruct the agent to check usages
before proposing any rename, move or delete, precisely because the failure is silent.

### The twelve tools

`dita_overview` · `dita_check_references` · `dita_map_structure` · `dita_resolve_key` ·
`dita_list_keys` · `dita_find_usages` · `dita_orphans` · `dita_validate` · `dita_deliverables` ·
`dita_build` · `dita_read_topic` · `dita_new_topic`

Plus four resources an agent can read without a tool call: `dita://overview`,
`dita://diagnostics`, `dita://keys`, `dita://structure`.

### Safety

Handing an agent tools over your documentation deserves scrutiny, so:

- **Eleven of twelve tools are read-only.** The exception can only create a file that does not
  already exist.
- **No tool deletes, renames, moves or publishes.** The capability is absent, not merely guarded,
  so no prompt can reach it.
- **Every path is confined to the workspace.** Traversal, absolute paths and symlink escapes are
  rejected — regression-tested in both directions.
- **Nothing leaves your machine.** It speaks to your editor over stdin and stdout and makes no
  network requests.

See [SECURITY.md](../SECURITY.md) for the full account.

---

## The HTTP API

Optional. Install with `dac interfaces --all`.

```bash
python3 scripts/docs-api.py --port 8765
curl localhost:8765/overview
```

Fifteen endpoints: `/overview`, `/stats`, `/check`, `/validate`, `/structure`, `/keys`,
`/keys/<key>`, `/uses/<target>`, `/orphans`, `/deliverables`, `/maps`, `/topics`, `/health`, and
`/` which lists them.

### When to use it rather than the CLI

- A documentation-health dashboard
- A CI job that posts the state of the docs somewhere
- A script in a language that is not Python
- Someone who wants the numbers without installing anything

### The constraints, and why

- **Read-only.** No write endpoints at all. Creating content and building live in the CLI and MCP
  server.
- **Localhost only** unless you pass `--host`, which prints a warning because there is no
  authentication.
- **Single-threaded.** It is a local convenience, not a service.

A documentation repository is not a web application, and an unauthenticated API over your content
should not be easy to expose by accident. If you need a shared endpoint, generate the JSON in CI
and publish that artefact instead.

---

## One engine, three surfaces

```
scripts/ditacore.py     find, parse, resolve keys, trace usages, check references,
      ▲                 validate, build, create topics
      │
      ├── scripts/docs             human-readable output
      ├── scripts/mcp-server.py    JSON-RPC over stdio
      └── scripts/docs-api.py      JSON over HTTP
```

`docs check`, `dita_check_references` and `GET /check` call the same function and return the same
findings. That is deliberate: the alternative is a CLI that says the docs are fine while the AI
assistant says they are broken.

It also means extending it is one change rather than three. If you add an operation, add it to
`ditacore.py` and expose it in each surface — see [CONTRIBUTING.md](../CONTRIBUTING.md).

---

## Troubleshooting

**`docs: command not found`** — use `./scripts/docs`, or add `scripts/` to your `PATH`.

**`docs check` reports nothing on a repository you know has problems** — check `--root`. Run
`docs stats` first; if it reports zero maps, you are pointed at the wrong directory.

**The MCP server does not appear in your IDE** — restart the editor. Then check the configuration
file exists and is valid JSON, and test the server directly with the `tools/list` command above.

**An MCP tool returns "path escapes the workspace"** — the path was outside the repository, or
`DITA_WORKSPACE` is wrong. Note that a *legitimate* relative path being rejected was a real bug on
macOS, fixed and regression-tested; if you see it, report it.

**The API will not start** — the port is in use. Pass a different `--port`.

More in [Troubleshooting](04-troubleshooting.md).
