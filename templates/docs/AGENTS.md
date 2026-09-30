# Repository conventions

Context for AI coding assistants (Cursor, Claude Code, Copilot) working in this repository.
Human contributors should read `docs/RUNBOOK.md` and `docs/CONTRIBUTING.md` instead.

## What this repository is

DITA XML documentation, built with DITA Open Toolkit {{DITA_OT_VERSION}}, validated and published
by CI. Set up by the DITA-as-Code Kit.

This is a **docs-as-code repository that deliberately keeps DITA** rather than migrating to
Markdown. Do not propose a Markdown migration. The reuse and conditional-processing semantics in
use here have no Markdown equivalent.

## Layout

```
{{REPO_LAYOUT}}
```

- `config/dita-ot-project.xml` - deliverables as declarative data. The source of truth for what
  gets published and which conditional filter applies to each output.
- `config/schematron/` - house rules, enforced in CI.
- `scripts/build.sh` - the same command CI runs. Change build behaviour here, not in the workflow.
- `.dac/` - kit state: detection results, capability probes, the action journal, blocker cards.

## Hard rules

**Never rename or move a `.dita` or `.ditamap` file with a plain filesystem operation.** Renaming
breaks every `href`, `conref` and `keyref` pointing at it. There is no warning at edit time. If a
rename is genuinely needed, update every reference in the same change, and verify with
`./scripts/validate.sh`.

**Never edit generated output.** `out/` and `temp/` are build artefacts.

**Never remove a `.ditaval` reference from `config/dita-ot-project.xml`.** A build without its
filter emits conditional content into the wrong output *and still exits zero*. This is the most
dangerous failure mode in DITA publishing because it is completely silent.

**Never add a `[formats]` section mapping `dita` to `.vale.ini`.** It silently breaks Vale's native
DITA handling. Keep the config scoped to `[*.dita]`.

**Preserve whitespace in mixed content.** DITA is whitespace-sensitive inside elements like `<p>`,
`<ph>` and `<uicontrol>`. Reflowing text there changes rendered spacing. Formatting is owned by
Prettier with `xmlWhitespaceSensitivity: strict` - do not reformat XML by hand or with another
tool.

## DITA specifics worth knowing

**Reuse.** `@conref` pulls in an element by direct reference; `@keyref` and `@conkeyref` do it
indirectly through a key defined in a map. Indirect is preferred because it survives file moves.
Keys **cannot** be defined in Markdown topicrefs.

**Conditional content.** `.ditaval` files filter by attribute. Every deliverable names its own.

**Markdown topics.** DITA-OT accepts them, but **the file extension is ignored** - a `.md` file
needs `format="markdown"` on its `topicref` or it is silently not part of the build.

**Topic types are semantic, not cosmetic.** A `<task>` must contain steps; a `<concept>` explains;
a `<reference>` tabulates. Schematron enforces this. If content does not fit its topic type, change
the topic type rather than fighting the rules.

## Diagnosing build errors

| Code | Meaning | Usual cause |
|---|---|---|
| `DOTJ041E` | Malformed `@conref` | Bad syntax in the reference |
| `DOTJ046E` | Unresolvable `@conkeyref` | Missing key definition in the map |
| `DOTX010E` | Missing `@conref` target | The target file or element was renamed or deleted |
| `DOTX028E` | Link with no valid target | Broken `href` |

**A zero exit code from `dita` is not proof that references resolved.** DITA-OT has historically
been silent about some unresolved references - unresolved conrefs in the PDF preprocess stage
emitted no message at all until a 2023 fix. This is why `scripts/validate.sh` greps for the codes
above instead of trusting the exit status. Keep it that way.

## Local versus CI differences

If a build passes locally and fails in CI, or vice versa, check the DITA-OT version first. Three
places must agree: `.dac/config.yml`, the CI workflow, and the version bundled in the writers'
editor. `dac doctor` compares them.

{{CCMS_AGENT_NOTE}}

## Validation layers

1. **Well-formedness** - `xmllint --noout`
2. **Grammar** - `dita validate` against the DITA DTD, needing `XML_CATALOG_FILES` set
3. **References** - a normalisation pass, checking for the codes above
4. **House rules** - Schematron via SchXslt
5. **Prose** - Vale, on `.dita` files only

Layer 5 has a real coverage gap: **`.ditamap` is not a Vale-supported extension**, so prose held
in maps is unlinted. Do not claim otherwise.

## Working on this repository

- Run `./scripts/validate.sh` before proposing a commit.
- Keep changes small and coherent.
- Match surrounding markup conventions.
- Prefer the semantic element over generic markup: `<filepath>` over a bare path in `<p>`,
  `<uicontrol>` over quoted UI labels. Semantic markup is what makes DITA worth its tag overhead -
  it can be styled, extracted and tested; plain text cannot.
