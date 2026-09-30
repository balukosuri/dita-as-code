# 5. Command reference

Every command, flag, file and diagnostic code. Look things up here.

---

## In an AI IDE

Inside Cursor, Claude Code or Copilot:

| Say this | What happens | Backed by |
|---|---|---|
| `dita as code` | Full run: audit, then offer setup | the skill, orchestrating the CLI |
| `dac audit` | Read-only audit. Changes nothing. | `dac.py audit` |
| `dac connect <link>` | Work out where content lives, fetch it if it is a repository | `dac.py connect` |
| `dac doctor` | Re-check the environment and diff against last time | `dac.py doctor` |
| `dac blockers` | List what is still waiting on another person | `dac.py blockers` |
| `dac rollback` | Undo the run, or one step of it | `dac.py rollback` |
| `dac interfaces` | Install the docs CLI, MCP server and HTTP API | `dac.py interfaces` |
| `dac state` | Compact summary of what DAC believes | `dac.py state` |
| `dac setup` | One-shot setup on a `dac/setup` branch | **the agent**, following `RECIPES.md` |
| `dac vendors research <name>` | Build a capability pack for an unrecognised tool | **the agent**, following `VENDORS.md` |

The last two are performed by the agent rather than by a command, because both need judgement:
setup has to decide whether to extend existing CI or leave it alone, and vendor research has to
read documentation and distinguish a real API from marketing copy. Everything else is a
deterministic command you can run yourself.

There is no `dac resume`. Re-running `dac setup` is the way to pick up a deferred step, and it is
safe because every recipe is idempotent.

## The `dac` command

```bash
python3 dita-as-code/scripts/dac.py <subcommand> [options]
```

### `connect`

Work out where the content lives and act on it.

```bash
dac.py connect --source "<url or path>" [--clone] [--dest DIR]
               [--full-history] [--kind git|vendor|local_dir] [--root DIR]
```

| Flag | Meaning |
|---|---|
| `--source` | Required. A Git URL, the address you log into to write, or a folder path. |
| `--clone` | Actually clone. Without it, prints the command for you to run. |
| `--dest` | Where to clone to. Defaults to the repository name. |
| `--full-history` | Clone all history. Default is shallow, which is all a pipeline needs. |
| `--kind` | Force the classification when detection guesses wrong. |

Recognises Git remotes over https and ssh, twelve authoring and delivery systems by hostname,
network shares, local folders, and published documentation sites.

**Refuses to clone into a non-empty directory.** Only https and ssh remotes are fetched.

### `audit`

Detect, probe, score, write blocker cards, write the audit report. **Read-only.**

```bash
dac.py audit [--root DIR] [--skip-egress] [--vendors LIST]
```

| Flag | Meaning |
|---|---|
| `--root` | Directory to audit. Defaults to the current one. |
| `--skip-egress` | Make no outbound network requests. Use offline or where policy forbids it. |
| `--vendors` | Comma-separated credentialed probes: `fluid-topics,oxygen` |

### `doctor`

Re-probe and diff against the last known good state. **The first thing to run when something
that worked stops working.**

```bash
dac.py doctor [--root DIR] [--skip-egress]
```

Reports tool version changes, network reachability changes, capability changes, and compares every
DITA-OT version in play — local, CI and the one your editor bundles. That last comparison is the
most common undiagnosed cause of "builds fine locally, fails on the server".

### `blockers`

List what is still waiting on another person, and what was degraded to a working alternative.

```bash
dac.py blockers [--root DIR]
```

### `rollback`

Undo a setup run. **Shows what it would do and changes nothing unless you pass `--yes`.**

```bash
dac.py rollback [--root DIR] [--step ID] [--yes]
```

Two paths, and it picks the right one:

- **On a `dac/*` branch** — deleting the branch removes everything. It prints the two commands, or
  runs them with `--yes`.
- **On an existing branch** — removes the files recorded in the journal, with two refusals: it
  will not delete a file you have edited since, and it will not touch anything it did not create.

### `interfaces`

Install the three interaction surfaces into the repository. See
[Your toolkit](07-your-toolkit.md).

```bash
dac.py interfaces [--root DIR] [--all] [--api] [--no-cli] [--no-mcp]
                  [--ide cursor|claude|vscode] [--dry-run]
```

Merges rather than clobbers an existing MCP config, is idempotent, and refuses to overwrite a
config file it cannot parse. `--dry-run` shows what would change without changing it.

### `state`

Compact summary of what DAC currently believes.

```bash
dac.py state [--root DIR]
```

---

## Individual scripts

Each stage runs standalone. Useful for scripting or debugging.

```bash
detect.py   --root DIR [--out FILE] [--quiet]
probe.py    --root DIR [--out FILE] [--skip-egress] [--vendors LIST] [--quiet]
score.py    --root DIR [--out FILE] [--detect FILE] [--probe FILE] [--quiet]
blockers.py --root DIR [--quiet]
report.py   --root DIR --kind audit|run [--out FILE] [--quiet]
connect.py  --source SRC [--clone] [--dest DIR] [--json] [--out FILE]
```

They run in that order and pass state through `.dac/state/`. Python 3.8+, standard library only —
nothing to install.

---

## Files DAC writes

### In your repository

| Path | What it is |
|---|---|
| `dac-audit.md` | The audit report. Always written, even on a read-only run. |
| `dac-report.md` | The run report, after setup. |
| `.dac/state/*.json` | Machine-readable state for each stage. |
| `.dac/journal.jsonl` | Every action taken, in order. |
| `.dac/blockers/BLK-*.md` | One card per blocker. |
| `.dac/blockers/BLK-*-request.md` | A message you can paste and send. |
| `.dac/config.yml` | Detected state with versions pinned. |
| `.dac/packs/` | Your own capability pack overrides. |

### Created by setup

| Path | What it is |
|---|---|
| `config/dita-ot-project.xml` | Deliverables as data, each naming its conditional filter. |
| `config/schematron/house-rules.sch` | Your house rules, enforced in CI. |
| `scripts/build.sh` | The same command CI runs. |
| `scripts/validate.sh` | Four layers of checking. |
| `scripts/sync-from-ccms.sh` | One-way CCMS export, archetype B only. |
| `.github/workflows/docs.yml` | Validate on proposal, build and publish on merge. |
| `.gitattributes` | Line-ending normalisation for XML. |
| `.prettierrc.yml` | Deterministic XML formatting. |
| `.husky/pre-commit` | Format and check before each commit. |
| `.vale.ini` | Prose rules, scoped to `*.dita` only. |
| `.devcontainer/` | One-click environment, same image as CI. |
| `docs/SETUP.md`, `RUNBOOK.md`, `CONTRIBUTING.md` | Guides for your team. |
| `docs/decisions/` | A record of every unattended decision, and how to reverse it. |
| `AGENTS.md`, `CLAUDE.md` | Repository conventions for AI assistants. |

---

## Environment variables

| Variable | Effect |
|---|---|
| `DAC_USE_DOCKER=1` | Build in a container instead of using local DITA-OT. |
| `DAC_OUTPUT` | Change the build output directory. Default `out`. |
| `DAC_CCMS_TOKEN` | CCMS credential for the sync script. **Never committed.** |
| `DAC_CCMS_BASE` | CCMS base URL for the sync script. |
| `DAC_SYNC_DEST` | Where synced content lands. Default `src`. |
| `SCHXSLT_JAR` | Path to the Schematron runner, enabling house-rule checks. |
| `XML_CATALOG_FILES` | Path to the DITA catalog. Required for reliable validation. |
| `DITA_HOME` | DITA-OT installation directory. |
| `FT_BASE_URL` | Override the Fluid Topics instance for probing. |

---

## The ten scored axes

| Axis | The question it answers | Weight |
|---|---|---|
| Source extractability | Can the content be got out as portable DITA without a human clicking? | 10 |
| Version control | Is the source in a system the company already uses? | 9 |
| Local build | Can a writer build on their own machine before pushing? | 7 |
| Automated build | Does a change build without anyone asking? | 8 |
| Structural validation | Are grammar, links and references checked automatically? | 8 |
| Editorial quality gates | Are style and terminology enforced rather than remembered? | 5 |
| Review workflow | Do changes get reviewed as diffs, by the right people? | 6 |
| Publish and deliver | Does approving a change publish it? | 7 |
| Reuse and dependencies | Is shared content managed deliberately? | 4 |
| Onboarding | Can a new writer get productive without a week of help? | 6 |

Levels: **0** absent · **1** manual · **2** scripted locally · **3** automated ·
**4** automated and enforced

Work order is `(ceiling − score) × weight`, highest first.

---

## DITA-OT diagnostic codes

The ones that actually matter, with their official meanings.

| Code | Meaning |
|---|---|
| `DOTX008E` | The resource cannot be loaded — a referenced file is missing. |
| `DOTX031E` | Resource not available to resolve link information. |
| `DOTJ046E` | `@conkeyref` cannot be resolved — the key is not defined. Reused content silently missing. |
| `DOTJ041E` | Malformed `@conref` syntax. |
| `DOTX010E` | Missing `@conref` target. |
| `DOTX028E` | Link with no valid target. |
| `DOTX009W` | Cannot retrieve a title from a target. |
| `DOTX023W` | Cannot retrieve navtitle from a target. |
| `DOTX027W` | Cannot retrieve link text from a target. |
| `DOTJ075W` | Absolute link without a correct `@scope`. |
| `DOTA069F` | Input resource cannot be located — usually a wrong path in the project file. |

`validate.sh` greps for the error codes specifically, because a zero exit code from `dita` is not
proof that references resolved.

---

## Blocker lanes

Every blocker gets exactly one lane, which tells you who has to act.

| Lane | Meaning |
|---|---|
| **Green** | You can do this yourself, right now, alone. |
| **Yellow** | Needs someone else's permission. DAC drafts the message. |
| **Red** | Needs budget. DAC writes the business case, including what the free fallback costs you. |

A blocker with no lane is a bug. So is a red blocker without a named price and a named fallback.

---

## Pinned versions

| Thing | Version | Why |
|---|---|---|
| DITA-OT | **4.4.1** | Current release, August 2026 |
| Java | **17** | What DITA-OT 4.4.x is built and tested against |
| Vale | **3.22.0+** | Floor for DITA ignore patterns |
| Node | **20+** | For the XML formatter chain |
| Container | `ghcr.io/dita-ot/dita-ot` | **Never** `ditaot/dita-ot` on Docker Hub — abandoned at 2.5.3 |

---

## Running the tests

```bash
python3 dita-as-code/fixtures/test_detection.py
```

22 tests covering vendor detection, the seven `connect` classifications, and specific regressions.
Standard library only, no pytest needed.
