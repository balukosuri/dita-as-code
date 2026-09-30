# Contributing to DAC

Contributions welcome. The most valuable ones are usually not code.

## What helps most

**Tell us what your ecosystem actually does.** The capability packs in `packs/` are the heart of
this project, and several were built from public documentation without a live system to verify
against. If you work with Componize, Bluestream XDocs, GlobalLink CCMS, Astoria, DITAToo, DX4,
RSuite, Sirius DITA or Tektur, you know things we had to mark `confidence: unverified`.

**Tell us when a report was wrong.** If DAC claimed a capability you do not have, or scored you in
a way the evidence does not support, that is a bug and we want it. Include `dac-audit.md` and
`.dac/state/detect.json` if you can share them.

**Tell us what broke.** Especially anything where DAC reported success but the outcome was wrong.
That class of bug is the one we care about most.

## Ground rules

These exist because the audience cannot easily check our claims, so a wrong claim does real damage.

**Never state a capability without evidence.** Every claim in a pack needs a source URL or
`confidence: unverified`. Marketing copy is not documentation: "comprehensive REST APIs" with no
endpoint reference, base URL or auth scheme is unverified, and the report must say so.

**Never promise a command that does not exist.** There is a test, `test_advertised_commands_all_exist`,
that fails if `SKILL.md` advertises a subcommand the CLI does not implement. It exists because we
shipped that mistake once.

**Name what a degrade path costs**, not just what it installs.

**Keep the standard library only.** No third-party dependencies in `scripts/` or
`templates/interfaces/`. A technical writer should never have to run `pip install` to audit their
own documentation. This also keeps the supply chain small enough to review.

**Python 3.8 is the floor.** It is what ships on older enterprise Linux. There is a compatibility
check in CI.

**A tool being installed is not evidence that content exists.** Findings are tagged `content` or
`toolchain`, and only `content` sets an archetype. We shipped the opposite once and it told
someone with an empty folder that their content was "already portable DITA sitting in files".

## Development

```bash
git clone <repo> && cd <repo>
python3 fixtures/test_detection.py      # 38 tests, no dependencies
```

The suite runs in a bare environment. It must pass both with and without a DITA toolkit on
`PATH`, because ambient tooling used to make several tests flaky:

```bash
python3 fixtures/test_detection.py
PATH="/path/to/dita-ot/bin:$PATH" python3 fixtures/test_detection.py
```

### Adding a capability pack

1. Copy the shape from `packs/oxygen.yml` and read `packs/_SCHEMA.md`.
2. Find the **official** documentation domain. Not a blog, not a reseller, not a comparison site.
3. Answer the operational questions: native source format, documented REST API with base URL and
   auth scheme, minimum role required, CLI, Git integration and whether it is source sync or
   output only, programmatic export, internal DITA-OT version and whether it is knowable.
4. Put every silent-failure mode in `gotchas`. A gotcha that merely wastes time is a note; a
   gotcha that produces wrong output while reporting success is a gotcha.
5. Add a `negative_guards` entry if the vendor's name collides with an unrelated product. We have
   one already: searching for the Bluestream XDocs API surfaces documentation for a mortgage
   document system, and an unsupervised research run will write a confident, fictional pack from
   it.

### Adding a detector

Add the function to `scripts/detect.py`, then add a fixture under `fixtures/` and a test. Model the
fixture on a **real** project layout and record where it came from in `fixtures/README.md` — every
existing fixture cites a public repository or a vendor document, so it can be corrected when a
vendor changes shape.

### Adding an operation to the three surfaces

Add it to `templates/interfaces/ditacore.py` only. The CLI, MCP server and HTTP API are thin
wrappers over that one engine, so they all get it and cannot disagree. Then expose it in each
surface and add a test.

### Tests that encode past bugs

Several tests exist because something real went wrong. Please do not delete one without
understanding why it is there; `fixtures/README.md` explains the notable cases. Examples:

- DAC detecting every vendor it documents when pointed at its own source
- A false "dead Gradle plugin" warning triggered by a code comment
- Path confinement rejecting legitimate paths under a symlinked root on macOS
- `--root` silently ignored because of an `argparse` `parents=` interaction

## Style

Match the surrounding code. A few specifics:

- Comments explain **why**, not what. If a line needs a comment saying what it does, rewrite the
  line.
- Writer-facing text is prose, not jargon. Assume no Git experience and no docs-as-code
  experience. Never say "simply" or "just".
- British-leaning spelling in prose is fine; keep it consistent within a file.
- No emoji.

## Pull requests

Small and focused. Say what changed and why. If it touches a pack, link the source that backs the
change. If it touches detection, include the fixture.

CI runs the suite on Python 3.8 through 3.13 and checks the compatibility floor.
