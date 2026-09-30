# DAC — The DITA-as-Code Kit

**Keep DITA. Keep your authoring tool. Get everything docs-as-code gives you.**

DAC is an agent skill for Cursor, Claude Code and Copilot. It looks at the DITA setup you already
have, tells you honestly what it can become, and then builds the missing pipeline around it in one
unattended run — version control, automatic checking, reviewable changes and automatic publishing.

It does not migrate you to Markdown. It does not ask you to leave Oxygen or cancel a CCMS licence.
It never touches your editor.

---

## Start here

**New to any of this?** → **[1. What is DITA-as-code?](docs/01-what-is-dita-as-code.md)**
No commands, just the idea. Written for someone who has never used Git.

**Ready to try it?** → **[2. Getting started](docs/02-getting-started.md)**
Install, find your content, first run, reading the report.

**Want to know how it works?** → **[3. How it works](docs/03-how-it-works.md)**
The pipeline, the archetypes, the safety rails, and the failure mode that matters most.

**Something went wrong?** → **[4. Troubleshooting](docs/04-troubleshooting.md)**
Every error encountered while building and testing this, with causes and fixes.

**Looking something up?** → **[5. Command reference](docs/05-command-reference.md)**
Every command, flag, file and diagnostic code.

**Using the CLI, MCP server and API?** → **[7. Your toolkit](docs/07-your-toolkit.md)**
Installing, configuring and using all three, end to end.

**Is it a CLI, an API or an MCP server?** → **[6. Architecture](docs/06-architecture.md)**
A precise answer about whose interface is whose.

---

## Try it in one command

Nothing is changed. The audit reads and reports.

```bash
git clone <this-repository> && ./dita-as-code/install.sh
python3 dita-as-code/scripts/dac.py audit --root /path/to/your/docs
```

Not sure where your docs are? Paste any link or path and let it work that out:

```bash
python3 dita-as-code/scripts/dac.py connect --source "https://yourcompany.heretto.com"
python3 dita-as-code/scripts/dac.py connect --source "https://github.com/acme/docs.git" --clone
```

---

## "I write in Oxygen / a CCMS. How do I even run this?"

DAC runs on your own computer, inside Cursor or Claude Code. It never connects to your editor. So
the only question is where your files physically are.

- **Oxygen, Arbortext, XMetaL, structured FrameMaker** → your content is already a folder. Open
  **that folder** and run DAC. Nothing to clone. Carry on writing exactly as before.
- **A network drive or SharePoint** → copy it to your computer first, then open the copy. Git is
  unreliable on a share.
- **A CCMS** (Heretto, IXIA, Tridion, AEM Guides, Paligo) → **there is nothing on your computer,
  and that is not your mistake.** Make an empty folder, open it, run DAC. It recognises what the
  emptiness means and sets up an export that copies your content down.
- **A repository you have never cloned** → `dac connect --source <url> --clone`.
- **Not sure** → run `dac audit` anyway. It changes nothing and its report tells you which case
  you are in.

Full detail in [Getting started](docs/02-getting-started.md#where-is-my-content).

---

## The core idea

Most advice about adopting docs-as-code assumes you are starting from nothing. Real writers start
from *something* — a CCMS with a seat licence, an Arbortext install someone bought in 2011, a
half-abandoned Git repository. The blocker is almost never "what is docs-as-code". It is:

> Given **my** tool, **my** licence tier and **my** permissions, what is the most docs-as-code-ish
> pipeline I can actually reach this quarter, and what exactly do I click?

Two facts shape everything:

**Capability varies per seat, not per product.** Two Oxygen users at the same company have
different powers depending on whether anyone bought a Scripting licence. A capability database is
necessary but never sufficient, so DAC probes reality.

**Editor lock is not format lock.** Arbortext, XMetaL, Oxygen and structured FrameMaker are all
GUI-first and none is meaningfully scriptable. But they all write real DITA to disk. So DAC
**never automates the editor** — it automates everything downstream of the save. That is what makes
an unattended run safe, and why Arbortext and XMetaL teams are far closer to this than they think.

---

## What you get

- `dac-audit.md` — what you have, what it can reach, what is in the way. Always written.
- `dac-report.md` — what works, what was degraded and why, what is blocked, three actions for Monday.
- `.dac/blockers/` — one card per blocker, each with a **copy-ready request message** naming the
  exact setting and the right person **by role**.
- A working pipeline: pinned DITA-OT, declarative deliverables, XML formatting, pre-commit hooks,
  validation, link checking, prose linting, Schematron, CI, publishing, devcontainer.
- `docs/SETUP.md`, `RUNBOOK.md`, `CONTRIBUTING.md`, decision records and `AGENTS.md` — written for
  a writer who has never used Git.

### Three ways to work with your DITA as code

This is the part that makes it usable day to day. All three share one engine, so they can never
give different answers.

```bash
docs check                    # every broken reference, with no Java needed
docs keys product-name        # where a key is defined, and everything that uses it
docs uses install.dita        # what breaks if you rename this
docs new task "Enable TLS"    # a topic with the correct skeleton for its type
docs build html               # through the same script CI runs
```

**An MCP server** so Cursor, Claude Code or Copilot answer from your content instead of guessing:

> "Is anything broken in the docs?" · "What would break if I rename install-overview.dita?" ·
> "Why is this conkeyref not resolving?"

Twelve typed tools, eleven of them read-only. Every path confined to the workspace.

**A read-only HTTP API** for a documentation-health dashboard or a CI job that reports state.

Install with `dac interfaces`. Full guide: **[Your toolkit](docs/07-your-toolkit.md)**.

---

## Verified, not assumed

Every capability claim in `packs/` carries a source URL or `confidence: unverified`.

The pipeline was tested against real documentation with Java 17 and DITA-OT 4.4.1 installed:

| Repository | Result |
|---|---|
| `robander/metadita-sampledocs` | 58% → **98%** after setup |
| `dita-ot/docs` — 267 topics, 57 maps | **88%**, already mature |
| `oasis-tcs/dita` — 23 RELAX NG grammars, restrictive licence | **88%**, hard mode |
| **Couchbase Server docs** — 1,383 topics, published by shell script | 58% → **95%** |

On Couchbase it built all 1,383 topics — authored against DITA-OT 2.0.1 — on 4.4.1 in 16 seconds,
producing 794 pages, and then found **36 errors and 15 warnings in their live published content**,
including a map referenced by their root map that does not exist.

```bash
python3 dita-as-code/fixtures/test_detection.py    # 22 regression tests
```

### The finding that shaped the whole design

A DITA build that omits its conditional filter emits the wrong content **and still exits
successfully**. Proven, not argued:

```
build exit code : 0            ← success
SECRET-INTERNAL-ONLY-CONTENT   ← found in the published HTML
```

And on Couchbase's real content, the same files with the same tool:

```
lenient build   : exit 0    ← success
strict validate : exit 1    ← failure
```

**Green and wrong is the most dangerous outcome in DITA publishing**, because nothing tells you.
It is why every deliverable DAC generates names its own filter, and why checking is always a
separate step from building.

---

## Honesty commitments

The audience typically has no prior docs-as-code experience and cannot easily check these claims,
so overclaiming is the fastest way to destroy the tool's credibility.

- **DITA 2.0 is not an OASIS standard.** The newest formal document is a 2018 public review draft;
  DITA 1.3 from 2015 remains current. LwDITA 1.0 is likewise unratified.
- **No CCMS syncs DITA source to Git.** Not one. Paligo's GitHub integration uploads published
  output as a zip; AEM's Git Connector runs inbound only. The export bridge is always built.
- **Archetype C is not fully docs-as-code.** Flare and unstructured FrameMaker teams get Git, CI,
  linting and publishing — not semantic diffs or component reuse.
- **There is no rich DITA authoring experience in VS Code.** Red Hat XML gives validation and
  navigation; the one purpose-built DITA extension has ~1,200 installs and a sole maintainer.
  Writers stay in their editor.
- **Paligo is DocBook 5.1, not DITA.**
- **Empty folders get no score.** DAC will not manufacture a verdict from nothing.

---

## Layout

```
SKILL.md              the orchestrator: detect, intake, probe, score, execute, verify, report
docs/                 this documentation set
references/           archetypes, recipes, vendors, blockers, placeholders, writer docs
scripts/              connect, detect, probe, score, blockers, report, dac (stdlib only)
packs/                15 vendor capability packs, user-overridable
templates/            CI, configs, hooks, scripts, devcontainer, writer docs
fixtures/             synthetic vendor projects plus the regression suite
```

Note that `templates/docs/` holds documents written **into your repository** for your team.
`docs/` — this set — is documentation **about DAC itself**.

---

## Non-goals

- Not a conversion engine. It orchestrates converters; it does not write XSLT.
- Not a CCMS replacement. It never tells anyone to cancel a licence.
- No writes back to a CCMS.
- No GUI automation, ever. A load-bearing constraint, not a limitation.
- No opinion on whether DITA is the right choice for you.

## Credit

The idea that DITA belongs in a docs-as-code model is not ours. It was argued by
[Tech Writer Koduje](https://techwriterkoduje.pl/dita-as-code/) and pioneered by
[DITA For Small Teams](http://www.d4st.org/). D4ST is also instructive in failure: it wired
client-side Git hooks to a stateful XQuery database, which is why DAC keeps every gate stateless
and CI-side.
