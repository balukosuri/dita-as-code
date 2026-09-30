# Capability pack schema

One YAML file per vendor. Packs ship with the skill, are overridable in the target repo at
`.dac/packs/`, and update independently of the skill because vendor APIs change faster than
release cycles.

## Required fields

```yaml
id: heretto                       # stable slug, matches detect.py finding vendor id
display_name: Heretto CCMS
archetype: [B, E]                 # A native-on-disk, B API-brokered CCMS,
                                  # C binary/proprietary, D delivery-side,
                                  # E server-side render service
source_format: dita              # dita | docbook | xhtml | proprietary | binary | mixed
last_verified: 2026-09-18
confidence: high                  # high | medium | low | unverified
```

`confidence` is load-bearing. `unverified` means the vendor advertises a capability but no
public documentation confirms it. DAC must say so in the report rather than acting on it.

## Optional sections

- `api` - base URL pattern, auth scheme, minimum role, pagination, rate limits
- `cli` - binaries and what they can do headlessly
- `git` - `source_sync` | `output_only` | `inbound_only` | `none`
- `export` - whether a full programmatic source export exists, and in what format
- `dita_ot` - whether the vendor runs DITA-OT internally and which version
- `render_service` - endpoint type, operations, auth (archetype E only)
- `detect` - credential-free fingerprints: files, dirs, env vars, install paths, content regexes
- `gotchas` - each with `id`, `severity`, `text`. These are the highest-value field in the pack.
- `separate_skus` - capabilities that cost extra, so DAC can say "you need to buy X"
- `docs` - source URLs backing every claim

## Rules

1. Every capability claim needs a `docs` URL or `confidence: unverified`.
2. `gotchas` describe silent failures, not inconveniences. A gotcha that only wastes time is a
   note; a gotcha that produces wrong output while reporting success is a gotcha.
3. Never record a capability from marketing copy. "Comprehensive REST APIs" with no endpoint
   reference is `confidence: unverified`.
4. `negative_guards` exist to stop automated vendor research writing a confident, fictional pack
   from a name collision.
