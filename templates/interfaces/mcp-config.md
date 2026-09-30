# Registering the MCP server with your AI IDE

DAC writes the right file for your tool. This page is what it writes, and where, so you can
check it or do it by hand.

The server gives Cursor, Claude Code and Copilot typed access to your DITA. Instead of guessing
from file contents, they can resolve a key, check every reference, walk the map structure, or find
out what breaks if you rename something.

---

## Cursor

Write `.cursor/mcp.json` in the repository:

```json
{
  "mcpServers": {
    "dita-docs": {
      "command": "python3",
      "args": ["scripts/mcp-server.py"],
      "env": {
        "DITA_WORKSPACE": "${workspaceFolder}"
      }
    }
  }
}
```

Restart Cursor. The server appears in Settings under MCP.

## Claude Code

Either add it to `.mcp.json` in the repository, which shares it with the whole team:

```json
{
  "mcpServers": {
    "dita-docs": {
      "command": "python3",
      "args": ["scripts/mcp-server.py"],
      "env": { "DITA_WORKSPACE": "." }
    }
  }
}
```

Or register it for yourself only:

```bash
claude mcp add dita-docs -- python3 scripts/mcp-server.py
```

## VS Code with Copilot

Write `.vscode/mcp.json`:

```json
{
  "servers": {
    "dita-docs": {
      "type": "stdio",
      "command": "python3",
      "args": ["scripts/mcp-server.py"],
      "env": { "DITA_WORKSPACE": "${workspaceFolder}" }
    }
  }
}
```

---

## Checking it works without an IDE

The server speaks JSON-RPC over stdin and stdout, so you can talk to it directly:

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 scripts/mcp-server.py
```

You should get a JSON object listing twelve tools. If you get nothing, run the same command
without the pipe and read the error — the usual cause is `DITA_WORKSPACE` pointing somewhere that
does not exist.

---

## What you can now ask

Once registered, these questions get answered from your actual content rather than guessed:

> Is anything broken in the docs?

> What would break if I rename `install-overview.dita`?

> Show me the structure of the user guide.

> Which topics use the key `product-name`?

> Why is this conkeyref not resolving?

> Create a task topic called "Configuring TLS" in the security folder.

> How much of our content actually uses reuse?

> Which topics are not in any map?

The one worth forming a habit around is the second. Renaming a DITA file breaks every reference
to it with **no warning at edit time**, and the tool descriptions tell the agent to check usages
before proposing any rename, move or delete.

---

## The tools

| Tool | What it does |
|---|---|
| `dita_overview` | Compact orientation: counts, types, reuse, deliverables, problem count |
| `dita_check_references` | Broken links, undefined keys, missing images, malformed XML |
| `dita_map_structure` | A map resolved into a tree, marking missing targets and cycles |
| `dita_resolve_key` | Where a key is defined, what it points at, where it is used |
| `dita_list_keys` | Every key, and which map defines it |
| `dita_find_usages` | What references a key or a file |
| `dita_orphans` | Topics no map references |
| `dita_validate` | Static check plus DITA-OT validation where available |
| `dita_deliverables` | What this repository publishes, and with which filters |
| `dita_build` | Build through the repository's own build script |
| `dita_read_topic` | One file, with resolved title and type |
| `dita_new_topic` | Create a topic with a valid skeleton for its type |

And four resources an agent can read without calling a tool: `dita://overview`,
`dita://diagnostics`, `dita://keys`, `dita://structure`.

---

## Safety

Worth knowing, because handing an agent tools over your documentation deserves scrutiny:

- **Eleven of the twelve tools are read-only.** The exception is `dita_new_topic`, and it can only
  create a file that does not already exist.
- **Nothing deletes, renames or publishes.** There is no tool for it, so an agent cannot do it
  through this server however it is prompted.
- **Every path is confined to the workspace.** Absolute paths, `../` traversal and symlink escapes
  are rejected rather than trusted. Verified: `dita_read_topic` with `../../../../etc/passwd`
  returns `Rejected: path escapes the workspace`.
- **Nothing leaves your machine.** The server talks over stdin and stdout to the editor on the
  same computer. It makes no network requests.
- **`dita_build` runs your own build script**, so it does exactly what CI does and nothing more.
