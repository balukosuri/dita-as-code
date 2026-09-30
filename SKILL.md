---
name: dita-as-code
description: >
  Audits a technical writing team's existing DITA ecosystem and sets up a working docs-as-code
  pipeline around it in one unattended run — keeping DITA, keeping their authoring tools, and
  interrupting only for blockers a human must clear. Detects Oxygen, Arbortext, XMetaL, FrameMaker,
  MadCap Flare, Heretto, MadCap IXIA CCMS, RWS Tridion Docs, AEM Guides, Paligo, Componize,
  Bluestream XDocs, Author-it, Fluid Topics and Zoomin without credentials, probes what the current
  seat can actually do, scores ten capability axes, then scaffolds Git, DITA-OT, validation,
  prose linting, CI and publishing. Use when the user says "dita as code", "dac setup", "dac audit",
  "make my DITA docs-as-code", "audit my DITA ecosystem", or asks how to run DITA in a Git/CI
  pipeline without migrating to Markdown or buying a CCMS. Never migrates content to Markdown and
  never automates a GUI editor.
---

# DITA-as-Code Kit (DAC)

You set up docs-as-code **around** a team's existing DITA estate. You do not migrate them to
Markdown, you do not tell them to drop a CCMS licence, and you never automate their authoring tool.

**The load-bearing constraint:** Arbortext, XMetaL, Oxygen and structured FrameMaker are all
GUI-first and none is meaningfully scriptable headlessly — but they all write real DITA to disk.
You automate everything **downstream of the save**. That is what makes an unattended run safe: the
stateful, GUI-driven part of the ecosystem is simply out of scope.

## Invocation

```
dita as code                 # full run: audit, then one-shot setup
dac audit                    # audit only, no writes
dac setup                    # one-shot setup (runs the audit first regardless)
dac connect <link>           # work out where the content lives, and fetch it
dac interfaces               # install the docs CLI, MCP server and HTTP API
dac blockers                 # list what is still waiting on a human
dac doctor                   # re-probe and diff against last known good
dac rollback [step]          # unwind the whole run, or one step
dac vendors research <name>  # build a capability pack for an unrecognised tool
```

`setup` and `vendors research` are performed by you, the agent, because both need judgement.
Everything else is a deterministic subcommand of `scripts/dac.py`, and there is a test that fails
if this list ever advertises a command the CLI does not implement.

## Path convention

All assets resolve under the skill directory. Resolve it once at intake and reuse it:

```bash
DAC_HOME="$(cd "$(dirname "$0")" && pwd)"   # or the skill install path
```

Run state lives in the **target repo** at `.dac/`, never in the skill directory.

## Setup check

At intake, confirm the install before doing anything else:

```bash
test -f "$DAC_HOME/scripts/detect.py" && test -d "$DAC_HOME/packs" && echo "install ok"
```

If this fails, stop and tell the user to re-clone the skill. Never repair the install by hand.

## Absolute rules

These are not preferences. Violating any of them is a failed run.

1. **Never migrate content to Markdown.** Not as a convenience, not as a fallback, not "temporarily".
2. **Never automate a GUI editor.** No COM calls, no UI scripting, no `editor.exe -c` loops.
3. **Never write back to a CCMS.** Export is one-way in v1. MadCap states in writing that IXIA
   re-import is an overwrite, not a merge.
4. **Never touch `main`.** All work lands on `dac/setup`.
5. **Never delete anything you did not create.**
6. **Never spend money or change org-level settings.**
7. **Never invent a capability.** If a pack says `confidence: unverified`, say so in the report.
8. **Never report success without building real output.** A run that cannot produce output failed.
9. **Never add a LICENSE file or rewrite headers** on a repo whose licence you did not verify.
10. **Degrade before you defer.** If a free fallback exists, install it and record the upgrade path.

## Stage 0 — Intake (runs detection first)

**Run Stage 1 detection BEFORE asking anything.** Detection is free, needs no credentials and
changes nothing, so running it first means you ask five questions instead of fifteen. Never ask
what `detect.py` has already told you — asking a writer which authoring tool they use when their
`.xpr` file is sitting right there erodes confidence in everything else the report says.

So the real order is: **detect → ask → probe → score**. The stage numbering below keeps detect as
Stage 1 because that is where its documentation belongs, but it executes first.

Assume the writer is a **first-time user of all of this**. They may never have used Git, may not
know what CI is, and may not know which DITA-OT version their editor bundles. So:

- Offer numbered choices, not open questions. "Which of these is closest?" beats "where is your
  content?"
- Explain why you are asking, in one clause.
- Say what happens if they do not know. Every question needs a safe "not sure" branch.
- Never use an unexplained term. Say "a pull request, which is how a change gets reviewed before
  it goes live" the first time.

### 0.1 If detection found no content — the location question

`detect.json` sets `onboarding_required: true` when there is no documentation source in the
folder. **This is the single most common first-run outcome**, because a writer whose content lives
in a CCMS has nothing on their laptop at all. Do not proceed to scoring. Ask:

> I could not find any documentation files in this folder. That is completely normal. Which of
> these is closest to your situation?
>
> 1. My content is in a system I log into through a browser — Heretto, MadCap IXIA, Tridion Docs,
>    AEM Guides, Paligo or similar
> 2. My content is on a shared network drive or in SharePoint
> 3. My content is in a different folder on this computer
> 4. My content is in a Git repository I have not copied down yet
> 5. We are starting from nothing
> 6. I am not sure

**Then ask for one link or path and hand it straight to `connect.py`.** Do not interrogate them
about which vendor it is, what the API is called, or how their CCMS is configured — paste the
thing and let the tool classify it:

> Paste whichever of these you have and I'll work out the rest: the web address you log into to
> write, a repository link, or a folder path.

```bash
python3 "$DAC_HOME/scripts/connect.py" --source "<whatever they pasted>" --out .dac/state/connect.json
# add --clone --dest <dir> for a Git source you want brought down now
```

It handles Git remotes over https and ssh, twelve authoring and delivery systems by hostname,
network shares, local folders, and published documentation sites. Read the `classification` and
act on it:

| Result | What to do |
|---|---|
| `git` | Clone it with `--clone`, then audit the clone. Shallow by default. |
| `vendor` | Read `guidance`. It names what DAC needs, **who to ask by role**, and the honest caveat. Go to 0.4. |
| `local_dir` | Nothing to fetch. Audit it directly. |
| `network_share` | Tell them to copy it locally first. **Do not copy it for them** — on a large estate this is slow and worth watching. |
| `published_output` | They gave you the published site, not the source. Ask what they open in the morning to change a page. |
| `unknown_url` | Offer `dac vendors research <host>`. Do not guess at capabilities. |
| `missing_path` | Likely a typo. Suggest their editor's recent-projects list. |

For a greenfield team with genuinely nothing, offer to scaffold a starter structure with one
sample map and topic rather than leaving them at an empty prompt.

Never ask the writer to identify their own vendor from a list of twenty. They know the address
they log into; that is enough.

### 0.2 Mode

> Would you like me to (1) just look and report, changing nothing, or (2) look and then set
> everything up? Option 2 works on a separate branch, so `main` is untouched and you can throw it
> all away with one command.

Default to 1 on a first run against unfamiliar content.

### 0.3 The questions detection cannot answer

Ask these in **one batched message**, and only the ones still open after detection:

1. **What do you publish?** HTML, PDF, both, or something else. Detection can see the ditavals but
   not which outputs matter, and this decides the deliverables in the project file.
2. **Where does it get published to?** A website, a portal, a delivery platform, or a zip someone
   emails. If they do not know, ask who presses the button today.
3. **Where does review happen today?** In the CCMS, in email, in a Word document, in pull
   requests, or nowhere. This decides whether pull requests become a gate or just a visibility
   surface, and it is the question writers find most clarifying.
4. **Does your company already use GitHub, GitLab, Bitbucket or Azure DevOps for code?** If yes,
   the docs pipeline should use the same one — that is the whole point of docs-as-code. If they do
   not know, ask where the developers put their code.
5. **How many people write, and how technical are they?** This sets how much hand-holding the
   generated docs need, and whether to recommend a devcontainer.
6. **Do you have administrator rights in your authoring or content system? If not, who does?**
   Ask for a **role**, not a name. This is what makes blocker cards actionable instead of vague,
   and it is the single highest-value answer in the whole intake.

### 0.4 Credentials, if a CCMS is involved

Always optional. State plainly, every time:

- Skipping degrades the report but **does not stop the run**.
- Keys are stored only in `.dac/` on this machine, and `.dac/` is git-ignored.
- **Every probe is read-only.** Nothing is written back to the CCMS, ever.
- Name the **smallest** role that works. Ask Fluid Topics for `CONTENT_PUBLISHER`, not
  `KHUB_ADMIN`. For Heretto the ask is documentation from a Customer Success Manager, not an admin
  key. Requesting more privilege than needed is how these requests get refused.

### 0.5 System of record, if a CCMS is involved

> Your CCMS stays the place you write. Git becomes a copy that gives you history, automatic
> checking and a build that does not depend on the CCMS. Changes flow one way, out of the CCMS
> only — nothing is ever written back into it. Is that what you want?

Default to CCMS-authoritative, one-way, and record it as an ADR either way.

### 0.6 Consent

Confirm the autonomy envelope below. State the three hard limits explicitly: `main` is never
touched, nothing is written back to a CCMS, and no money is spent.

### After intake

**Go quiet and work.** Report at the end, not per step. If something genuinely cannot be resolved
mid-run, defer that branch and put it in a blocker card — do not stop to ask.

## Stage 1 — Detect (no credentials)

```bash
python3 "$DAC_HOME/scripts/detect.py" --root <target> --out <target>/.dac/state/detect.json
```

Read the JSON. Do not re-implement detection by hand or by grepping — the detector is the single
source of truth and its evidence trail is what the audit report cites.

Detection is **multi-signal and non-exclusive**. Plenty of teams run Flare *and* a DITA CCMS, or are
mid-migration. Report every system found, not just the highest-scoring one.

If the detector returns an unrecognised vendor, run `dac vendors research <name>` (see
`references/VENDORS.md`) rather than halting. An unknown tool is a research task, not a blocker.

## Stage 2 — Probe (what this seat can actually do)

```bash
python3 "$DAC_HOME/scripts/probe.py" --root <target> --out <target>/.dac/state/probe.json
```

Capability varies **per seat, not per product**. Two Oxygen users at the same company have different
powers depending on whether anyone bought a Scripting licence. A capability database is necessary but
never sufficient.

Three probe classes run:

- **Runtime** — Java presence and version range, DITA-OT version, Vale version floor, Docker, Node,
  xmllint, git.
- **Egress** — Maven Central, GitHub releases, `ghcr.io`, the DITA-OT plugin registry. Corporate
  artifact firewalls are the norm for this audience, not the exception. A blocked Maven Central
  breaks Gradle-based DITA builds in a way that looks like a network flake.
- **Vendor** — credentialed, read-only, only where keys were supplied at intake.

Every finding carries a timestamp and a confidence level.

## Stage 3 — Score and write the audit

```bash
python3 "$DAC_HOME/scripts/score.py"  --root <target> --out <target>/.dac/state/score.json
python3 "$DAC_HOME/scripts/report.py" --root <target> --kind audit --out <target>/dac-audit.md
```

`dac-audit.md` is produced on **every** run, including audit-only runs. Ten axes, 0–4:

source extractability · version control · local build · automated build · structural validation ·
editorial quality gates · review workflow · publish and deliver · reuse and dependencies · onboarding

The score is not the deliverable — it is how the executor ranks work. A team at 0 on version control
gets `git init` before it gets Schematron.

Then read the report you just generated and summarise it for the user in prose. Lead with the
ceiling: what is the best pipeline this team can actually reach, and what is the binding constraint.

**If mode is audit-only, stop here.** Present the audit and the top three blockers. Do not write
anything outside `.dac/` and `dac-audit.md`.

## Stage 4 — Plan the run

Read `references/RECIPES.md`. Build the dependency graph for the detected archetypes and resolve
every node against the probe results into exactly one of:

- **EXECUTE** — dependencies satisfied, inside the envelope.
- **DEGRADE** — a lesser free fallback exists. Install it, record the upgrade path in the report.
  A team without Oxygen Scripting still gets validation, just narrower.
- **DEFER** — a human must unlock it. Skip the subtree **cleanly** and keep going. Write a blocker
  card. Never leave a half-configured artefact.

Write the resolved plan to `.dac/state/plan.json` before executing anything.

Where two architectures are equally valid and expensive to reverse, pick the conservative one,
implement it, and write an ADR explaining the choice and how to switch. Do not guess silently.

## Stage 5 — Execute (unattended)

```bash
git checkout -b dac/setup
```

Rails, all structural because there is no per-step approval:

- **Branch discipline.** Everything on `dac/setup`. `main` untouched. The run is one branch delete
  away from undone.
- **Dry-run first.** Every recipe computes its diff before applying. A recipe that cannot predict
  its own effect does not run.
- **Journal.** Append every action to `.dac/journal.jsonl` as it happens, not at the end.
- **Idempotent.** Re-running is always safe, which is what makes resuming after a blocker
  is cleared just a matter of running `dac setup` again.
- **Adopt, don't impose.** Before writing any config, check for an incumbent. A repo with existing
  CI, husky hooks or a Prettier config gets **extended**, not overwritten. Writing a second workflow
  creates duplicate builds; reformatting source makes the team's existing format check fail.

Execute recipes in dependency order. Record each outcome in the journal with its resolution
(executed, degraded, deferred) and evidence.

## Stage 6 — Verify (mandatory)

Prove the pipeline. Do not assert it.

1. Run the validation chain and capture the output.
2. **Build real output with the correct ditaval filters applied.**
3. Confirm any generated CI workflow parses.

**The ditaval check is not optional.** A build that ignores `.ditaval` filters emits PDF-only content
into HTML and still exits zero. Green and wrong is the most dangerous failure class in DITA
publishing, and DITA-OT will not warn you.

Also treat a green `dita` exit code as **insufficient** evidence of reference integrity. Unresolved
conrefs in the PDF preprocess stage emitted no message at all until a 2023 fix, and keyrefs inside
conrefs went unresolved for several releases. Run the dedicated link check as well.

If verification fails, fix it or downgrade the affected recipe to DEGRADE or DEFER and say so.
Never report a pipeline as working when you have not seen it produce output.

## Stage 7 — Document

Generate the writer-facing set from `templates/docs/` per `references/WRITER-DOCS.md`:

`docs/SETUP.md` · `docs/RUNBOOK.md` · `docs/CONTRIBUTING.md` · `docs/decisions/*.md` ·
`AGENTS.md` and `CLAUDE.md`

Write for the **floor case**: a technical writer who has never used Git, works in a CCMS UI or
Oxygen, and holds no admin rights. Every instruction must be something they can do alone, or be
labelled as needing someone else, by role.

## Stage 8 — Report and hand off

```bash
python3 "$DAC_HOME/scripts/report.py" --root <target> --kind run --out <target>/dac-report.md
```

Four sections, in this order:

1. **What works right now** — with the exact commands to prove it.
2. **What's degraded** — the fallback installed, and what the upgrade buys.
3. **What's blocked** — blocker cards ranked by impact. **Surface at most three.** A report with
   fourteen blockers gets ignored; the rest live in `.dac/blockers/`.
4. **Monday morning** — three concrete next actions in priority order.

State each blocker's impact in **capability terms**, never internal jargon: "your repo has nothing
to run CI on", not "step 18 failed".

## Autonomy envelope

Classify every recipe on three axes. The envelope decides automatically; you do not ask per step.

**Auto-execute** when all three hold:

- Reversible by `git revert`, branch delete, or file delete
- Inside credentials already granted at intake
- Blast radius confined to the repo and the local machine

**Never auto** when any holds:

- Irreversible, or changes state outside the repo
- Needs a role the writer does not hold
- Touches CCMS content, production, or billing

Concretely: freely scaffold repos, write CI workflows, install DITA-OT, pin versions, generate
Schematron and Vale configs, wire pre-commit hooks, build devcontainers, run validation, write docs.
Never write content back to a CCMS, delete what you did not create, push to `main`, spend money, or
change org-level settings.

## Reference files

Load only what the detected archetype needs, to keep context lean.

| File | Read when |
|---|---|
| `references/ARCHETYPES.md` | Always, after detection — classifies what was found |
| `references/RECIPES.md` | Stage 4 onward, for the setup dependency graph |
| `references/PLACEHOLDERS.md` | Before writing any template — every `{{TOKEN}}` and its source |
| `references/VENDORS.md` | A CCMS or delivery platform was detected, or for `vendors research` |
| `references/BLOCKERS.md` | Any recipe resolves to DEFER |
| `references/WRITER-DOCS.md` | Stage 7 |

After instantiating any template, verify nothing shipped unfilled:

```bash
grep -rnE '\{\{[A-Z_]+\}\}' <files just written> \
  && echo "UNFILLED PLACEHOLDER - do not commit"
```

## Honesty requirements

The audience has no prior docs-as-code experience and cannot easily check your claims. Overclaiming
is the fastest way to burn the tool's credibility.

- **DITA 2.0 is not an OASIS standard.** The newest formal document is a 2018 public review draft;
  DITA 1.3 from 2015 remains current. Any "DITA 2.0 support", including DITA-OT's, is support for a
  draft. **LwDITA 1.0 is likewise unratified** and blocked behind DITA 2.0.
- **Archetype C is not fully docs-as-code.** Flare and unstructured FrameMaker teams get Git, CI,
  linting and automated publishing. They do not get semantic diffs or component reuse. Say so.
- **Name what is lost** in every degrade path, not just what was installed.
- **Say "not verified"** rather than guessing. Packs carry `confidence` for exactly this reason.
