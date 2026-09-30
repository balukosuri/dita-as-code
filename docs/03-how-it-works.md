# 3. How it works

What happens inside a run, and why it is built this way. Useful if you want to trust it, extend
it, or explain it to someone who will ask hard questions.

---

## The one constraint everything follows from

> **DAC never automates your editor. It automates everything downstream of the save.**

Arbortext, XMetaL, Oxygen and structured FrameMaker are all GUI-first, and none can be meaningfully
driven from a script. XMetaL's automation runs inside the running application as Windows COM
macros. Arbortext's `-c` flag still launches the desktop program.

But all four write ordinary DITA files to disk. So DAC does not need them. It picks up from the
saved file.

Three consequences, all of them good:

1. **Unattended runs are safe.** The stateful, GUI-driven, hardest-to-automate part of the
   ecosystem is simply out of scope.
2. **Your workflow does not change.** No retraining, no new editor, no migration.
3. **Arbortext and XMetaL teams are much closer to this than they think.** Their tool is often
   described as legacy, but XMetaL 20.0 bundles DITA-OT 4.2.2 — newer than *every* cloud CCMS
   surveyed. IXIA defaults to 2.5.4, AEM Guides ships 3.3.2, Heretto caps at 3.7.4.

## The pipeline

```
detect → ask → probe → score → plan → execute → verify → document → report
```

Detection runs **before** the questions. That is deliberate: detection is free and needs no
credentials, so running it first means DAC asks five questions instead of fifteen. Asking a writer
which editor they use when their Oxygen project file is sitting right there erodes trust in
everything else the report says.

### Detect — no credentials needed

Walks the folder once, then evaluates vendor fingerprints against what it found. It reads the
filesystem, environment variables and well-known install paths. It writes nothing.

It identifies the real source format (actual DITA versus Flare's XHTML versus Paligo's DocBook),
the authoring tool and its bundled DITA-OT version, the CCMS if any, existing CI, and existing
quality gates.

Two design points worth knowing:

**Detection is non-exclusive.** Plenty of teams run Flare *and* a DITA CCMS, or are mid-migration.
DAC reports every system found, not just the loudest.

**A tool being installed is not evidence that content exists.** Findings are tagged as either
`content` (this system holds the content, so it sets the archetype) or `toolchain` (a tool is
installed here, which says nothing about where content lives). Conflating those two once made DAC
tell someone with a completely empty folder that their content was "already portable DITA sitting
in files", purely because `dita` was on their `PATH`.

### Ask — once, then silence

Everything DAC needs is gathered in a **single batched intake**. Never drip-fed across the run,
because a writer abandons a run that keeps interrupting them.

It only asks what detection cannot infer: where the content is if it is not on disk, what outputs
matter, where review happens today, whether the company already uses GitHub or GitLab for code,
and — the highest-value question in the whole intake — **who has administrator rights if you do
not**. That last answer is what makes a blocker card name a real person instead of a vague role.

### Probe — what *this* seat can actually do

Capability varies **per seat, not per product**. Two Oxygen users at the same company have
different powers depending on whether anyone ever bought a Scripting licence. So a lookup table of
vendor capabilities is necessary but never sufficient — DAC tests reality.

Three kinds of probe:

- **Runtime** — is Java present and in the supported range, which DITA-OT, is Vale new enough, is
  Docker actually running rather than merely installed
- **Network** — can this machine reach Maven Central, GitHub releases, the container registry and
  the plugin registry
- **Vendor** — read-only, credentialed, only where keys were given

The network probe earns its place. Corporate artifact firewalls are the norm for this audience,
not the exception, and a blocked download looks exactly like a random network failure. On the
machine DAC was developed on, Maven Central and the npm registry are both transparently mirrored
through a corporate proxy and work fine — while one specific artifact path is denied by policy.
DAC distinguishes "proxied and working" from "actually blocked", because telling someone their
network is broken when it is merely mirrored sends them to the wrong colleague.

### Score — ten axes, and an honest ceiling

Ten areas, each 0 to 4:

source extractability · version control · local build · automated build · structural validation ·
editorial quality gates · review workflow · publish and deliver · reuse and dependencies ·
onboarding

**The score is not the deliverable.** It is how DAC decides what order to do things in. A team at
zero on version control gets `git init` before it gets Schematron rules, because everything else
depends on it.

Each axis has a **ceiling** set by the archetype, and ceilings below 4 are honest limits rather
than aspirations:

- Archetype B (CCMS) is capped at 2 on review workflow, because subject-matter experts review
  inside the CCMS, not in pull requests
- Archetype C (Flare, Author-it, binary FrameMaker) is capped at 1 on source extractability and
  reuse, because the source is not DITA

Presenting those as achievable would be dishonest and would be discovered at the worst moment.

### Plan — execute, degrade or defer

Every setup step resolves into exactly one of three outcomes:

- **Execute** — dependencies met, inside the permission envelope
- **Degrade** — a lesser free alternative exists. Install it, and record what an upgrade would buy.
- **Defer** — a human must unlock it. Skip that branch **cleanly** and carry on.

Two rules make this safe:

**Degrade before you defer.** A team with no Oxygen Scripting licence still gets validation, just
narrower.

**A deferred branch is cleanly absent, never half-built.** The pipeline that exists at the end of
a run is always a working pipeline.

**Blockers never stop the run.** If DAC halted at the first locked door, a writer missing one API
key would end up with nothing at all.

### Execute — unattended, with structural safety

There is no per-step approval, so the safety has to be structural rather than procedural:

- **Branch discipline.** Everything on `dac/setup`. Your main branch is never touched. The entire
  run is one branch delete away from undone.
- **Dry-run first.** Every step computes its effect before applying it. A step that cannot predict
  its own effect does not run.
- **Journal.** Every action appended to `.dac/journal.jsonl` as it happens.
- **Idempotent.** Re-running is always safe.
- **Adopt, don't impose.** Before writing any config, DAC checks for an incumbent. A repository
  with existing CI gets **extended**, not overwritten — writing a second workflow gives you
  duplicate builds, and if the existing one includes a format check, reformatting source makes it
  fail.

Hard limits it will never cross: your main branch, writing back to a CCMS, deleting anything it
did not create, spending money, or changing organisation-level settings.

### Verify — prove it, do not assert it

DAC runs the validation chain and **builds real output with the correct conditional filters
applied**. A run that cannot produce output does not report success.

The filter check is not optional, and here is why.

### The failure mode that matters most

A DITA build that omits its `.ditaval` filter emits the wrong conditional content into the output
**and still exits successfully.** DITA-OT does not warn you.

This was verified rather than assumed. A topic containing
`<p audience="internal">SECRET-INTERNAL-ONLY-CONTENT</p>` was built without the filter:

```
build exit code : 0        ← success
grep SECRET out/a.html : 1 ← the internal-only text is in the published page
```

With the filter applied, correctly excluded.

**Green and wrong is the most dangerous outcome in DITA publishing**, because nothing tells you.
It is why every deliverable DAC generates names its own filter, and why "does it build?" is never
treated as the same question as "is it right?"

A related trap: a zero exit code from `dita` is **not** proof that cross-references resolved.
Unresolved `conref`s in the PDF stage produced no message at all until a fix in 2023. So DAC runs
a separate reference check looking for the specific diagnostic codes, rather than trusting the
exit status.

### Document, then hand off

Generates the writer-facing guides, decision records for every unattended choice, and an
`AGENTS.md` so your team's AI assistant understands the repository afterwards.

Then `dac-report.md`: what works with commands to prove it, what was degraded and what an upgrade
buys, what is blocked ranked by impact — **at most three surfaced**, because a report with fourteen
blockers gets ignored — and three concrete actions.

---

## The five archetypes

Hardcoding vendors does not scale, so recipes attach to archetypes rather than brands. An
unfamiliar CCMS gets classified and handled rather than hitting a dead end.

| | What it is | Ceiling |
|---|---|---|
| **A** | Native DITA on disk — Oxygen, Arbortext, XMetaL, FrameMaker-as-XML, Content Fusion | **4 everywhere** |
| **B** | API-brokered CCMS — Heretto, IXIA, Tridion, AEM Guides, Paligo | 3–4, review capped at 2 |
| **C** | Binary or proprietary — Flare, Author-it, unstructured FrameMaker | 3 on build, 1–2 on review and reuse |
| **D** | Delivery platform — Fluid Topics, Zoomin, portals | Publishing only |
| **E** | Server-side render service — Arbortext PE, FrameMaker Publishing Server, Oxygen PE | Different CI shape |

Archetype E is assigned **only on evidence**, never because a vendor is capable of it. Oxygen is
archetype A unless a Publishing Engine licence key is actually found. Claiming a render service a
team does not own is exactly the overclaim that destroys confidence in a report.

## What gets written into your repository

```
config/dita-ot-project.xml    deliverables as data, each naming its own filter
config/schematron/            your house rules, enforced in CI
scripts/build.sh              the same command CI runs
scripts/validate.sh           four layers of checking
.github/workflows/docs.yml    validate on proposal, build and publish on merge
.prettierrc.yml               deterministic XML formatting
.husky/pre-commit             format and check before each commit
.devcontainer/                one-click environment, same image as CI
docs/                         SETUP, RUNBOOK, CONTRIBUTING, decisions
AGENTS.md, CLAUDE.md          repository conventions for AI assistants
.dac/                         state, journal, blocker cards

scripts/ditacore.py           the shared engine behind the three surfaces below
scripts/docs                  a command line over your DITA
scripts/mcp-server.py         typed tools for Cursor, Claude Code and Copilot
scripts/docs-api.py           read-only JSON over HTTP (optional)
.cursor/mcp.json              registers the MCP server with your IDE
```

Those last five are the point of the whole exercise: a pipeline you cannot query is a pipeline you
will not trust. See [CLI, API and MCP](06-architecture.md) for what each one gives you.

Two of these deserve explanation.

**`dita-ot-project.xml` instead of build arguments.** Deliverables become declarative data that a
person or an AI assistant can read, instead of build logic buried in a shell script. It is also
what makes the conditional-filter mistake impossible to make by accident.

**Prettier with the XML plugin.** "XML diffs are unreadable in pull requests" is the single most
cited reason people believe DITA cannot work this way — and it is already solved in practice.
DITA-OT's own documentation repository normalises every DITA file this way on commit. Deterministic
formatting is what makes review possible, and it is the highest-value single change in the whole
setup.

---

Next: [Troubleshooting](04-troubleshooting.md) ·
[Command reference](05-command-reference.md) ·
[CLI, API and MCP](06-architecture.md)
