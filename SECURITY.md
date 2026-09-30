# Security

DAC touches credentials, installs an MCP server, and can start an HTTP API over your content.
That deserves scrutiny, so this page states plainly what it does, what it refuses to do, and where
the real risks are.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Email the maintainers, or use GitHub's private vulnerability reporting on this repository. Include
what you found, how to reproduce it, and what you think the impact is. You will get an
acknowledgement within a few days.

## What DAC does with credentials

- **They are optional.** Every credentialed probe can be skipped. Skipping narrows the report; it
  never stops the run.
- **They stay on your machine.** Credentials are read from the environment or from `.dac/`, and
  are never transmitted anywhere except to the vendor API they belong to.
- **`.dac/` is git-ignored** by the installer, specifically because it can contain API tokens.
  Check this holds in your repository before committing.
- **Nothing is written into a committed file.** The generated CCMS sync script reads
  `DAC_CCMS_TOKEN` from the environment and refuses to run without it, rather than accepting a
  token as an argument where it would land in shell history.
- **Every vendor probe is read-only.** DAC does not write back to a CCMS at all.

DAC asks for the **smallest** role that works, deliberately. Fluid Topics gets a request for
`CONTENT_PUBLISHER` rather than `KHUB_ADMIN`; Heretto gets a documentation request to a Customer
Success Manager rather than an admin key. Over-requesting privilege is both a security problem and
a good way to get the request refused.

## The MCP server

The server DAC installs into your repository is the component most worth reviewing, because it
hands an AI agent tools over your documentation.

- **Eleven of twelve tools are read-only.** The exception, `dita_new_topic`, can only create a
  file that does not already exist.
- **There is no tool that deletes, renames, moves or publishes.** An agent cannot do those things
  through this server however it is prompted, because the capability is absent rather than
  guarded.
- **Every path argument is confined to the workspace.** Absolute paths, `../` traversal and
  symlink escapes are rejected. This is regression-tested in both directions: that traversal is
  refused, and that legitimate relative paths under a symlinked root are accepted.
- **It makes no network requests.** Communication is JSON-RPC over stdin and stdout with the
  editor on the same machine.
- **`dita_build` runs your own `scripts/build.sh`**, so it does exactly what CI does and nothing
  more.

If you are reviewing it, the security-relevant function is `safe_path()` in
`templates/interfaces/mcp-server.py`. It is short on purpose.

## The HTTP API

Optional, not installed by default, and deliberately constrained.

- **Read-only.** There are no write endpoints. Creating content and building are available through
  the CLI and MCP server, not here.
- **Binds to `127.0.0.1`** unless you pass `--host` explicitly. If you do, it warns you that there
  is no authentication.
- **No authentication, by design.** It is a local convenience, not a service. Do not put it behind
  a public address or a reverse proxy.
- Query parameters that resolve outside the repository are rejected with a 400.

If you need a documentation-health endpoint for a team, generate the JSON in CI and publish that
artefact. Do not expose this server.

## What DAC will never do

These are enforced constraints, not conventions:

- Never push to `main`, or any branch other than `dac/setup`
- Never write back to a CCMS
- Never delete a file it did not create
- Never delete a file you have edited since it was created
- Never spend money or change organisation-level settings
- Never automate a GUI application
- Never transmit your content anywhere

## Running third-party code

DAC generates CI workflows and a devcontainer that download pinned tools: DITA-OT from its GitHub
releases, the container image from `ghcr.io/dita-ot/dita-ot`, Vale from its releases, and npm
packages for the XML formatter.

Two notes:

- **Versions are pinned**, not floating, so an upgrade is a visible change in a diff.
- **Review the generated workflow before merging it.** It runs in your CI with your secrets
  available. This is true of any generated pipeline and is worth doing once.

DAC itself has **no third-party dependencies**. Every script is Python standard library only,
which is partly a usability decision and partly a supply-chain one.

## Scope

Security issues in DAC's own code are in scope. Vulnerabilities in DITA-OT, Vale, a vendor's CCMS
or an authoring tool should go to that project or vendor, though we are glad to be told so the
capability packs can carry a warning.
