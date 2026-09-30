# Changelog

## 0.1.0 — unreleased

First public release.

### What it does

- **Audit** — detects the ecosystem without credentials, probes what the current seat can
  actually do, scores ten capability axes against an honest per-archetype ceiling, and writes a
  report for a writer who has never used Git.
- **Connect** — takes a repository URL, a CCMS web address, a network share or a folder, works out
  which it is, and either clones it or explains exactly what is needed and who to ask.
- **Setup** — builds the pipeline: pinned DITA-OT, declarative deliverables, deterministic XML
  formatting, pre-commit hooks, validation, link checking, prose linting, Schematron, CI,
  publishing and a devcontainer.
- **Interfaces** — installs three ways to work with the content: a `docs` command, an MCP server
  for Cursor, Claude Code and Copilot, and an optional read-only HTTP API. All three share one
  engine so they cannot disagree.
- **Rollback** — undoes a run. Dry by default; never deletes a file it did not create or one the
  writer has since edited.

### Coverage

15 vendor capability packs, each claim carrying a source URL or `confidence: unverified`.
Five archetypes so an unfamiliar tool is classified rather than hitting a dead end.

### Verified against real documentation

Tested with Java 17 and DITA-OT 4.4.1 installed, against `robander/metadita-sampledocs`,
`dita-ot/docs`, `oasis-tcs/dita` and Couchbase Server's documentation. The last of those —
1,383 topics published for years by a hand-written shell script pinning DITA-OT 2.0.1 — built
successfully on 4.4.1, and the static reference check found 513 problems in that live content.

The highest-severity warning was proven rather than asserted: a build omitting its `.ditaval`
filter leaked internal-only content into published HTML and exited 0.

39 regression tests, standard library only, passing on Python 3.8 through 3.13 and with or without
a DITA toolkit on `PATH`.

### Known limits

- Archetype B export bridges are scaffolded but only exercised against documentation, not a live
  CCMS tenant. Verification wanted.
- Archetype C (MadCap Flare) recipes are written but untested on a Windows runner.
- AEM Guides UUID builds need a bespoke link checker; the static check is not UUID-aware.
- Componize, Bluestream XDocs and several smaller CCMSs are `confidence: unverified`.
- DocBook to DITA conversion is scoped but never performed.
