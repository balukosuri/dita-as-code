# Fixtures

Synthetic projects for the vendors that cannot be obtained self-serve, plus the detection
regression suite.

```bash
python3 fixtures/test_detection.py
```

## Why these are synthetic

Of the commercial tools DAC must detect, almost none can be evaluated without a sales call:

| Tool | Self-serve trial? | Usable as a testbed? |
|---|---|---|
| Oxygen XML | yes, web form, key by email | yes, and the only one that runs on Apple Silicon |
| Oxygen Scripting | no, sales contact only | no |
| Heretto | no, 30-minute sales call first | no |
| Paligo | no, the "free trial" is a demo booking form | no |
| MadCap Flare | 30-day, but Windows-only | not without a Windows VM and licence |
| Fluid Topics | no free tier or public sandbox | its public read API is usable, see below |

So the fixtures below are modelled on **verified real-world file structures**, not invented.
Each one's provenance is recorded so it can be corrected when a vendor changes layout.

## Provenance

| Fixture | Modelled on |
|---|---|
| `flare-project/` | The real `.flprj` in `Gigaspaces/xap-docs` on public GitHub — root element, attribute set and child blocks as they actually appear. Topics are XHTML `.htm`, which is the discriminator that matters. |
| `xmetal-project/` | The XMetaL Customization Guide plus real `.ctm`/`.mcr` files in `NCIOCPL/cdr-client`. Note the INI is **versioned** (`xmetal60.ini`), which is the fingerprint most tools get wrong. |
| `arbortext-project/` | PTC's documented `custom/` subdirectory structure, plus an `e3config.xml` carrying the `AllowedFunctions` allowlist that actually governs Publishing Engine access. |
| `ixia-workspace/` | IXIA's documented `preferences.properties` keys and the `content\authoring` export layout with its three sidecar types. |
| `aem-uuid/` | Adobe's documented `GUID-` filename pattern **and** UUID-valued `href` attributes — the second part is what breaks filename-based link checking. |
| `paligo-export/` | The documented `publication--<lang>.xml` layout with the DocBook 5.1 namespace, which is the conclusive proof it is not DITA. |
| `framemaker-binary/` | Binary `.fm`/`.book` with no DITA XML, exercising the archetype discriminator. |

## Real testbeds used alongside these

Fixtures verify fingerprints. Real repositories verify the pipeline. Three were used:

- **`robander/metadita-sampledocs`** (Apache-2.0) — fast inner loop, maintained by a DITA 2.0
  spec co-editor.
- **`dita-ot/docs`** (Apache-2.0) — 267 topics, 57 maps, 89 files using conref, 168 using keyref,
  a real 766 KB Oxygen `.xpr`, five workflows, husky and `@prettier/plugin-xml`. It doubles as a
  free Oxygen detection fixture and as the gold-standard pipeline to copy.
- **`oasis-tcs/dita`** — deliberate hard mode. 23 RELAX NG grammars that the build installs over
  DITA-OT's bundled doctypes, and **not an open-source licence** (OASIS RF on Limited Terms), so it
  also verifies that repository setup is a correct no-op on restrictively licensed content.

There is also one genuinely free, no-procurement vendor API worth knowing about:
`https://docs.fluidtopics.com/api/khub/maps?lang=en` is a live Fluid Topics instance answering
unauthenticated reads, which gives the delivery-side probe a real endpoint to test against.

## Tests that encode real bugs

Several cases exist because detection got it wrong first, against real repositories:

- **`test_no_self_detection`** — the first implementation flagged Zoomin from DAC's own reference
  files, because a bare product name matches prose *about* a vendor.
- **`test_gradle_plugin_variant_precision`** — `dita-ot/docs` names `eerohele` in a *comment*
  explaining what it replaced, and a substring check produced a false "you are on the dead plugin"
  warning.
- **`test_ditaval_wiring`** — `dita-ot/docs` applies filters from `build.gradle` rather than a
  project file. That is valid, and must not be reported as a high-severity problem.
- **`test_arbortext_without_pe_is_not_archetype_e`** — claiming a render service a team does not
  own is the kind of overclaim that destroys trust in the report.
