# 6. CLI, API and MCP — what DAC is and is not

You asked whether DAC ultimately creates a CLI, an API and an MCP server to make docs-as-code
happen. The short answer is **partly, and the distinction matters**, so this page is precise about
it.

---

## The short answer

**Yes — all three, for your repository.** That is the goal of the tool, and it is what the setup
run installs.

| | Does DAC have one, for itself? | Does DAC **create** one for your docs? |
|---|---|---|
| **CLI** | **Yes.** `dac connect / audit / doctor / state / blockers / rollback` | **Yes.** A `docs` command: `docs check`, `docs keys`, `docs uses`, `docs build`, `docs new` |
| **MCP server** | No. Not needed — its stages already emit JSON. | **Yes.** `scripts/mcp-server.py`, 12 tools and 4 resources, registered with your IDE |
| **API** | No. It is a local setup tool, not a service. | **Yes.** `scripts/docs-api.py`, a read-only JSON API over HTTP |
| **Agent skill** | **Yes.** The primary way writers invoke it. | Writes `AGENTS.md` so your repo is legible to any AI assistant |

So the distinction is about **whose** interface: DAC itself needs only a CLI and an agent skill,
because it is a one-time setup tool. **Your documentation** gets all three surfaces, because that
is what makes DITA workable as code day to day.

All three of yours are thin wrappers over one shared engine, `scripts/ditacore.py`, so they
cannot drift apart or give different answers. Add an operation once and every surface gets it.

## The distinction that actually matters

There are three different things being conflated when people ask this question:

**1. How you talk to DAC.** Two surfaces: an agent skill (you type `dita as code` in Cursor) and a
command line (`python3 scripts/dac.py audit`). The agent surface exists because the audience is
technical writers rather than engineers. The CLI exists because deterministic work should be
reproducible and testable, and because CI cannot talk to a chat window.

**2. How DAC talks to your ecosystem.** This is where CLIs and APIs come in — as things DAC
*consumes*, not things it produces:

| System | What DAC uses |
|---|---|
| DITA-OT | Its command line — `dita --project=...` |
| Heretto | REST API, plus webhooks in NotifyPull mode |
| MadCap IXIA | REST API at `/rest/1.0` |
| Tridion Docs | ISHRemote, the vendor's PowerShell module |
| AEM Guides | REST API with Adobe IMS OAuth |
| Paligo | REST API v2 — admin only |
| Fluid Topics | REST API, plus the `ftpub` CLI |
| MadCap Flare | `madbuild.exe` |
| Arbortext PE | HTTP request functions |
| Oxygen | Its scripting CLI, if licensed |

DAC is a **client** of all of these. It writes no APIs of its own.

**3. What DAC builds for you.** Two things: a **pipeline** (build script, validation script, CI
workflow, declarative project file, formatting, hooks, and optionally a one-way CCMS export) and
the **three interaction surfaces** below.

So the accurate sentence is: *DAC is a CLI and agent skill that uses vendors' CLIs and APIs to
build you a pipeline plus a CLI, an MCP server and an API over your own documentation.*

## Your three surfaces

Installed by recipes R21, R22 and R23. All three call into `scripts/ditacore.py`.

### The `docs` command

```bash
docs stats          docs check        docs keys product-name
docs tree           docs validate     docs uses install.dita
docs build html     docs orphans      docs new task "Configuring TLS"
```

The most valuable one is `docs check`, because it resolves every reference **statically** — no
Java, no toolkit, nothing installed. A writer can check their work on day one. Run against
Couchbase Server's documentation it found **513 problems**: 299 missing link targets, 211 missing
images, 2 files with malformed XML, and an undefined key meaning reused content was silently
missing from a published page.

### The MCP server

Twelve typed tools and four resources, so Cursor, Claude Code or Copilot answer from your content
instead of guessing:

> "Is anything broken in the docs?" · "What would break if I rename install-overview.dita?" ·
> "Why is this conkeyref not resolving?" · "Which topics use the key product-name?"

This is the surface that matters most for DITA specifically, because **the questions writers have
are graph questions**. Where is this key defined? What references this file? The answer lives in
the relationships between files, not inside any one of them, so an agent reading raw text cannot
answer reliably.

The tool descriptions also teach the agent two DITA-specific traps it would otherwise get wrong:
renaming a file breaks every reference with no warning at edit time, and a passing build is not
evidence that references resolved.

Safety: eleven of the twelve tools are read-only, the twelfth can only create a file that does not
exist, nothing deletes or renames or publishes, every path is confined to the workspace, and
nothing leaves the machine.

### The HTTP API

Read-only JSON over HTTP, for a documentation-health dashboard, a CI job reporting state, or a
script in another language. Bound to localhost unless you say otherwise, no write endpoints, and
single-threaded — a documentation repository is not a web application, and an unauthenticated API
over content should not be easy to expose by accident.

## Why DAC itself has no API or MCP server

Because DAC is a **one-time setup tool**, not a runtime component. Once your pipeline exists, DAC
is out of the loop: your CI does the work and you run `dac doctor` occasionally. An API would need
hosting, authentication and an availability commitment, none of which help anyone set up a
pipeline once. And its stages already emit JSON, so an agent reads `.dac/state/detect.json`
directly.

The MCP server that matters is the one over **your documentation**, which is why that is the one
that got built.

Worth knowing about the landscape: **no vendor in this ecosystem ships an MCP server.** Not
Heretto, Paligo, Oxygen, MadCap or Adobe. The only prior art is DitaCraft's standalone server and
two build-it-yourself community tutorials. So the server DAC installs in your repository is
roughly first of its kind.

## Why a CLI and not only an agent skill

Three reasons, and they are the reason the split exists at all:

**Reproducibility.** An agent asked to "detect the ecosystem" might reason differently on Tuesday.
`detect.py` cannot. When a report says 1,383 topics and 76 maps, that is countable and checkable.

**Testability.** There are 22 regression tests over the deterministic parts. You cannot
regression-test a prompt the same way, and several of those tests exist because real bugs were
found and must not come back.

**CI.** The generated pipeline runs on a server with no agent available. `scripts/build.sh` and
`scripts/validate.sh` must work as plain commands.

The division is deliberate:

> **The CLI does the doing. The agent does the judging and the explaining.**

Anything deterministic — fingerprinting, API calls, scaffolding, validation, rollback — lives in
the CLI so it is reproducible, testable and auditable. Anything requiring interpretation — reading
an unusual folder structure, classifying an unknown vendor, writing a blocker explanation a writer
will actually act on, deciding whether to extend existing CI or leave it alone — lives in the
agent.

## The layers, end to end

```
You, in Cursor or Claude Code
        │
        ├── agent skill (SKILL.md)  ── judgement, explanation, intake
        │
        └── dac CLI (Python, stdlib) ── detect, probe, score, blockers, report, connect
                    │
                    ├── consumes: DITA-OT CLI, vendor REST APIs, vendor CLIs, git
                    │
                    └── produces, in your repository:
                            ├── the pipeline: build + validate scripts, CI, project file,
                            │   formatting, hooks, devcontainer, writer docs
                            └── three surfaces over your DITA, sharing one engine:
                                    scripts/docs            a command line
                                    scripts/mcp-server.py   typed tools for your AI IDE
                                    scripts/docs-api.py     read-only JSON over HTTP
```

The bottom layer is the deliverable. DAC's job is to build it and then get out of the way.

## One engine, three surfaces

Worth stating explicitly, because it is the reason the three cannot disagree:

```
scripts/ditacore.py     the operations: find, parse, resolve keys, trace usages,
      ▲                 check references, build, validate, create topics
      │
      ├── scripts/docs             argparse, human-readable output
      ├── scripts/mcp-server.py    JSON-RPC over stdio, typed tool schemas
      └── scripts/docs-api.py      HTTP, JSON responses
```

Every surface is a thin translation layer. `docs check`, `dita_check_references` and
`GET /check` all call the same function and return the same findings — which is how you avoid the
situation where the CLI says the docs are fine and the AI assistant says they are broken.

It also means adding an operation is one change, not three. And all of it is standard-library
Python, so a writer never has to run `pip install` to ask a question about their own
documentation.

---

Back to [the README](../README.md) · [How it works](03-how-it-works.md) ·
[Command reference](05-command-reference.md)
