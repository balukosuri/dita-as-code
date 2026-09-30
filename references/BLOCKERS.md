# Blockers

Blockers are the writer-facing product of a one-shot run. Per-step approval is gone, so the
blocker card carries all the weight the approval cards used to.

## The two rules that make one-shot safe

**Degrade before you defer.** If a free or lesser fallback exists, install it and record the
upgrade rather than blocking. A team without an Oxygen Scripting licence still gets validation,
just narrower.

**A deferred branch is cleanly absent, never half-built.** A skipped subtree leaves either nothing
or an inert, clearly-labelled placeholder. The pipeline that exists at the end of a run is always
a working pipeline.

A blocker **defers a branch of the dependency graph and the run continues**. DAC does not stop at
the first locked door. If it did, a writer missing one API key would end up with nothing.

## Lanes

Every blocker gets exactly one lane. The lane tells the writer who has to act, which is the only
thing they actually need to know.

- **Green** - the writer can do this themselves, right now, alone.
- **Yellow** - needs someone else's permission or action. DAC drafts the request message.
- **Red** - needs budget. DAC writes the business case, including what the money buys and what
  the free fallback costs them.

A blocker with no lane is a bug. So is a red blocker without a named price and a named fallback.

## Card format

Write to `.dac/blockers/BLK-<id>.md`. Keep it to one screen.

```
BLK-04 - Heretto content export is not running
--------------------------------------------------------------------
WHAT'S      Nightly CCMS to Git sync. Without it, your repository has
MISSING     CI and linting but nothing to run them on.

WHY         The v1 API that reads content is not publicly documented.
            The v2 API you have access to covers publishing only.

WHO         Your Heretto Customer Success Manager. NOT your Heretto
            administrator - this is a documentation request, not a
            permissions change.

FIX         Ask them for the v1 API documentation, and to enable
            webhooks in NotifyPull mode for your organisation.
            Then run setup again - it is idempotent, so it will
            pick up only the part that was deferred:  dac setup

DRAFT       A ready-to-send message is at
MESSAGE     .dac/blockers/BLK-04-request.md

MEANWHILE   Everything else is live. Export one map manually from the
            CCMS, drop it in src/, and you can exercise the whole
            validate-build-publish chain today.

COST        None. Documentation and configuration only.
TIME        About 5 minutes for them, once they see the message.
LANE        yellow
--------------------------------------------------------------------
```

## Writing rules

**State impact in capability terms, never internal jargon.** "Your repository has CI and linting
but nothing to run them on" - not "step 18 failed" or "the export recipe returned non-zero".

**Name the right person, by role.** This is where DAC earns its keep, and getting it wrong wastes
the writer's credibility with a colleague:

- **Heretto** - Customer Success Manager for the v1 API docs and webhook enablement. An
  administrator cannot help; the documentation is gated behind the CSM relationship.
- **Paligo** - a Paligo administrator, because the API requires an admin user with no exceptions.
- **AEM Guides** - whoever owns your Adobe Developer Console, usually IT rather than the docs
  team. This is OAuth Server-to-Server credential provisioning.
- **Arbortext PE** - the administrator who maintains `e3config.xml`, because access is governed by
  the `AllowedFunctions` allowlist rather than by credentials.
- **MadCap Flare CI** - whoever owns licensing, because `madbuild -activate` works only on an
  enterprise floating licence.
- **IXIA** - a System Administrator, since the Export scenario is admin-only by default.
- **Fluid Topics** - a tenant admin, but ask for `CONTENT_PUBLISHER` only. Requesting
  `KHUB_ADMIN` asks for far more privilege than publishing needs and is more likely to be refused.

**Cap the surfaced list at three.** A report with fourteen blockers gets ignored. Rank by impact
and put the rest in files.

**Always give a "meanwhile".** A blocker the writer cannot act on today must still leave them
something to do. This is what keeps a deferred branch from feeling like a dead end.

**Never invent a contact name.** Name the role, and let the writer map it to a person.

## Draft request messages

Write to `.dac/blockers/BLK-<id>-request.md`. These get pasted into Slack or email by someone who
may not fully understand the request themselves, so they must stand alone.

Requirements:

1. **Name the exact setting, path or menu location.** Not "grant API access" but "generate a
   service account key under Settings, Integrations, API Keys".
2. **State the scope honestly, and that it is read-only** where true. This is the single biggest
   objection you will get, so answer it before it is asked.
3. **Say what it unblocks, in business terms.** "This lets our documentation build automatically
   when the product ships" beats "this enables the export recipe".
4. **Keep it under 150 words.** Longer messages do not get read.
5. **No jargon the recipient does not already use.** An administrator does not need to know what
   a ditaval is.

Template:

```markdown
# Request: <one line, what you need>

Hi <role>,

I'm setting up automated checking and publishing for our documentation, so that it
builds and validates itself whenever we make a change.

To finish, I need one thing: <exact setting, with its full path>.

**What it does:** <one sentence>
**Access level:** <read-only / specific role name> - this does not allow changing or
deleting content.
**Why it matters:** <business outcome in one sentence>

If it's easier to do this on a call, I'm happy to walk through it.

Thanks,
<name>
```

## Standard blockers

These recur often enough to be pre-written. Generate them from the probe results.

| ID | Trigger | Lane | Degrade available |
|---|---|---|---|
| `BLK-no-build-path` | no Java 17+ and no working container | green | none - this one is genuinely critical |
| `BLK-container-only` | Docker works, no local Java | green | yes, container builds |
| `BLK-java-version` | Java present but outside 17 to 21 | green | yes, try anyway and record the risk |
| `BLK-no-prose-lint` | Vale present but no DITA-OT on PATH | green | yes, lint in CI only |
| `BLK-vale-below-floor` | Vale older than 3.22.0 | green | yes, no ignore patterns for DITA |
| `BLK-no-xml-formatter` | no Node or npm registry blocked | yellow | no - review stays painful |
| `BLK-maven-denied` | Maven Central policy-denied | yellow | yes, use the DITA-OT CLI path, not Gradle |
| `BLK-oxygen-scripting` | Oxygen present, no scripting key | red | yes, DITA-OT validate plus xmllint |
| `BLK-heretto-v1-api` | Heretto detected, no v1 access | yellow | partial, manual export for testing |
| `BLK-paligo-admin` | Paligo detected, non-admin key | yellow | none - hard wall, no author-level API |
| `BLK-aem-oauth` | AEM Guides, no IMS credentials | yellow | none |
| `BLK-flare-floating-licence` | Flare CI on a non-floating licence | red | yes, a pinned non-ephemeral runner |
| `BLK-pe-allowlist` | Arbortext PE not allowlisted | yellow | yes, local DITA-OT with different output |

## Anti-patterns

- A blocker that just says "permission denied". Say which permission, held by whom, granted where.
- A red blocker with no price. If you cannot find the price, say "quote only" and name the vendor
  contact route.
- Surfacing a blocker for something DAC successfully degraded. That belongs in the degraded
  section, not the blocked section. Conflating them makes the run look like it failed when it
  did not.
- Halting the run. Never. Defer the branch and carry on.
