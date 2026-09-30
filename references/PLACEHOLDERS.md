# Placeholders

Every `{{PLACEHOLDER}}` in `templates/` and where its value comes from.

**A shipped `{{PLACEHOLDER}}` is a bug.** After instantiating any template, grep the target repo
for `{{` and fail the run if anything remains:

```bash
grep -rnE '\{\{[A-Z_]+\}\}' <files you just wrote> \
  && echo "UNFILLED PLACEHOLDER - do not commit"
```

Where a value cannot be determined, do not guess and do not leave the token. Either omit the
surrounding block entirely, or substitute an explicit, honest fallback such as
`your team's usual channel`.

## Core

| Placeholder | Source |
|---|---|
| `{{DITA_OT_VERSION}}` | The pinned version written to `.dac/config.yml`. Prefer the version bundled by the detected editor so local, CI and editor output agree. |
| `{{DEFAULT_BRANCH}}` | `git symbolic-ref --short refs/remotes/origin/HEAD`, falling back to the current branch. |
| `{{ROOT_MAP}}` | The repository's primary `.ditamap`, **relative to the repository root**. Pick the map that is not referenced by any other map; if several qualify, ask at intake rather than guessing. Used by `build.sh`, `validate.sh` and the CI workflows, all of which run from the repository root. |
| `{{SOURCE_DIR}}` | The directory containing `.dita` topics, from the detector's sample paths. |
| `{{DITA_HOME}}` | `probe.json` runtime, or the container path `/opt/app` when building in the image. |
| `{{REPO_NAME}}` | The repository directory name, lowercased and hyphenated. |
| `{{EDITOR_NAME}}` | `display_name` of the highest-confidence archetype A finding. If none, use `your XML editor`. |
| `{{HELP_CHANNEL}}` | Ask at intake. Fall back to `your team's usual channel`. |
| `{{CONREF_COUNT}}` | `dita.conref_files`. Used to make the reuse argument concrete for developers rather than abstract. |
| `{{REPO_LAYOUT}}` | The actual directory tree, two levels deep. **Never the template's idealised layout** - a wrong map is worse than none. |

## Deliverables and filters

**Everything inside `dita-ot-project.xml` is relative to that file's own directory, not to
the repository root.** These placeholders are deliberately named `*_FROM_PROJECT` or
documented as such, because mixing the two frames is the easiest mistake to make here and it
produces a `DOTA069F` error pointing at a directory *above* the repository, which reads as a
missing file rather than a path bug.

| Placeholder | Source |
|---|---|
| `{{ROOT_MAP_FROM_PROJECT}}` | The same map as `{{ROOT_MAP}}`, but relative to the project file's directory. With the project file in `config/`, this is `../` plus `{{ROOT_MAP}}`. **The placeholder carries the whole path including the `../` - never add another prefix when filling it.** |
| `{{HTML_DITAVAL}}` | The `.ditaval` governing HTML output, relative to the project file's directory. |
| `{{PDF_DITAVAL}}` | The `.ditaval` governing PDF output, relative to the project file's directory. |
| `{{PRIMARY_DELIVERABLE}}` | The `output/@href` of the deliverable to publish, typically `html5`. Note `output/@href` is the one exception - it resolves against the CLI output directory, so the CI artefact path is `out/<this>`. |

If the repository has ditavals but no discoverable mapping from filter to deliverable, **stop and
ask**. Guessing here produces a build that succeeds and publishes the wrong content, which is the
worst outcome available.

If the repository has no ditavals at all, omit the `<profile>` elements rather than inventing a
filter.

## CCMS, archetype B only

Omit every one of these, and the blocks containing them, when no CCMS is detected.

| Placeholder | Source |
|---|---|
| `{{CCMS_VENDOR}}` | The detector's vendor id, for example `heretto` or `ixia-ccms`. |
| `{{CCMS_NAME}}` | The vendor's `display_name`, for the ADR and writer docs. |
| `{{CCMS_BASE_URL}}` | From intake. Never hardcode a tenant URL into a committed file - read it from `DAC_CCMS_BASE` at runtime. |
| `{{CCMS_USER}}` | From intake. Same rule: environment, not committed. |
| `{{CCMS_ROW}}` | A runbook table row describing the sync schedule, or empty. |
| `{{CCMS_VERSION_NOTE}}` | The version-drift warning naming the CCMS's internal DITA-OT version, or empty. |
| `{{CCMS_AGENT_NOTE}}` | CCMS-specific guidance for `AGENTS.md`, or empty. |
| `{{IXIA_EXPORT_PATH}}` | The IXIA `Export` transformation scenario path. Probe; do not assume. |
| `{{ISH_CLIENT_ID}}` | Tridion Docs OAuth client id, from intake. |
| `{{AEM_CLIENT_ID}}` | AEM Guides IMS client id, from intake. |
| `{{AEM_PATH}}` | The AEM Assets path holding the DITA content. |

**Credentials are never written into a committed file.** Tokens come from the environment at run
time. The sync script reads `DAC_CCMS_TOKEN` and refuses to run without it, by design.

## ADRs

| Placeholder | Source |
|---|---|
| `{{NUMBER}}` | Sequential, zero-padded to four digits. |
| `{{TITLE}}` | A one-line statement of the decision, written as a decision rather than a topic. |
| `{{DATE}}` | ISO date of the run. |
| `{{REVERSIBLE}}` | `yes`, `no`, or an honest qualifier such as `yes, but not cheaply once people rely on it`. |
| `{{CONTEXT}}` | The situation and the constraint that forced a choice. |
| `{{DECISION}}` | What was chosen, in the active voice. |
| `{{ALTERNATIVES}}` | Each option considered **with the real reason it was rejected**. "Not chosen" is not a reason. |
| `{{RATIONALE}}` | Why this one, including what it deliberately gives up. |
| `{{HOW_TO_SWITCH}}` | Concrete steps to reverse it. This is the most valuable field in the file - an ADR without it reads as an excuse rather than a decision. |
