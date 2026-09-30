# Archetypes

Hardcoding vendors does not scale. DAC classifies every tool into one of five archetypes, and
recipes attach to **archetypes, not brands**. An unfamiliar CCMS gets classified and handled
rather than hitting a dead end.

A team is frequently in more than one archetype at once. That is normal, not an error. Take the
best ceiling any detected archetype allows per axis, and record which archetype sets the cap.

---

## Archetype A - Native DITA on disk

*DITA-OT + Oxygen · Arbortext Editor · XMetaL · structured FrameMaker saved as XML · Oxygen
Content Fusion · the d4st lineage*

The content is already portable DITA. **The editor being GUI-only and unscriptable is irrelevant
to the pipeline**, because DAC automates from the save onward. This is the single most important
reframe DAC offers: Arbortext and XMetaL shops are usually far closer to docs-as-code than they
believe.

**Ceiling: 4 across all ten axes.** Full one-shot setup, few blockers.

Two things to say out loud to these teams:

- XMetaL 20.0 bundles DITA-OT 4.2.2 and Oxygen 28.1 bundles 4.4.0, while IXIA defaults to 2.5.4,
  AEM Guides ships 3.3.2 and Heretto caps at 3.7.4. Their "legacy" desktop editor has a far more
  modern toolkit than the cloud CCMSs.
- If they are an Oxygen shop, Content Fusion may already give them a Git-native workflow that is
  shorter than anything DAC would build. Check before building a parallel pipeline.

---

## Archetype B - API-brokered CCMS

*Heretto · MadCap IXIA · RWS Tridion Docs · AEM Guides · Paligo (DocBook) · Componize ·
Bluestream XDocs*

The CCMS stays the system of record. Git becomes a mirror and the automation substrate.

**The defining fact: no CCMS surveyed syncs DITA source to Git.** Not one. Paligo's GitHub
integration uploads published output as a zip. AEM's Git Connector runs inbound only, Git into
AEM. So the export bridge is always something DAC builds, never something it switches on. That is
the core value DAC delivers to these teams, and no vendor will do it for them.

Direction policy is an explicit ADR:

- **One-way, CCMS to Git** - safe, and the default. Enables CI, linting, PR review of diffs, and
  disaster recovery.
- **Two-way** - out of scope for v1. MadCap states in writing that IXIA re-import "is an
  overwrite, not a merge."

**Ceiling: 3 to 4 on most axes.** Review workflow is capped at 2, because subject-matter experts
review inside the CCMS UI, not in pull requests. Source extractability is capped at 3, because an
export is always a copy with a lag, never the live source.

Blockers here are almost always **permissions**, which is why the draft-request-message feature
matters most in this archetype. Get the recipient right: for Heretto the ask goes to a Customer
Success Manager, not an administrator.

---

## Archetype C - Binary or proprietary format

*MadCap Flare · Author-it · unstructured FrameMaker `.fm`*

You can get Git, CI, linting and automated publishing. You **cannot** get clean semantic diffs or
true component reuse. DAC says so plainly rather than pretending.

**Ceiling: 3 on build and CI, 1 to 2 on review and reuse, 1 on source extractability.**

One important correction to the usual framing: **Flare has first-class native Git**, with UI
branching, and MadCap's own docs describe running GitFlow internally. Do not imply these teams
lack version control. What they lack is semantic diffs and component reuse. Several archetype B
CCMSs have a worse Git story than Flare does.

Flare specifics: `madbuild -project X.flprj -target Y`, credentials in a JSON file rather than
inline, pre/post build events as extension points, and a pinned Windows runner unless the org has
an enterprise floating licence - the only licence on which `madbuild -activate` works.

---

## Archetype D - Delivery-side

*Fluid Topics · Zoomin (sunsetting) · Heretto Portal · AEM Sites*

An ingest endpoint. DAC wires the publish step and treats it as the deploy target. This is usually
the easiest link in the chain.

Fluid Topics ingests DITA natively and has a real CLI (`ftpub`). Ask for `CONTENT_PUBLISHER`, not
`KHUB_ADMIN` - publishing does not need admin, and a smaller ask gets granted faster.

**Zoomin is a special case: detecting it raises a migration-risk finding, not a recipe.**
Salesforce ended renewals on 1 September 2025 for the portal, In-Product Help, the API and
Headless. Do not wire a publish step to a product being wound down.

Note that Document360, ReadMe and GitBook do **not** ingest DITA. Using them as a DITA output host
means a DITA-OT HTML or Markdown transform first, and losing the structured source.

---

## Archetype E - Server-side render service

*Arbortext Publishing Engine · FrameMaker Publishing Server · Oxygen Publishing Engine ·
Heretto DITA-OT Cloud*

Neither an authoring tool nor a CCMS: a build endpoint you call instead of running the toolkit
yourself. This changes the shape of the CI job - it becomes "call the render service and collect
the artefact" rather than "install DITA-OT and run it". No toolkit install, no version pinning,
but new concerns around endpoint auth, queueing and artefact retrieval.

In enterprises this is often the fastest route to automated publishing, because the licensed
engine already exists on a server that nobody has wired to Git.

**Assign E only on evidence**, never because a vendor is capable of it. Oxygen is archetype A
unless a Publishing Engine or PDF Chemistry licence key is actually found. Arbortext is archetype
A unless an `e3config.xml` or a reachable PE endpoint is found. Claiming a render service a team
does not own is exactly the kind of overclaim that destroys trust in the report.

Two service-specific traps worth knowing:

- **Arbortext PE has no `f=compose`.** Publishing goes out as
  `f=java&class=com.arbortext.e3c.Application`. Access is governed by the `AllowedFunctions`
  allowlist in `e3config.xml`, so valid credentials with a non-allowlisted function still fail.
- **FrameMaker Publishing Server allows only one task in the schedule queue at a time**, and needs
  roughly a one-second gap between consecutive tasks. Parallel CI publish jobs will fail.

---

## Unknown vendors

`dac vendors research <name>` runs a live documentation crawl, fills a capability-pack template,
classifies the archetype, and marks everything `confidence: unverified` until a probe confirms it.
During a one-shot run this happens automatically - an unrecognised tool becomes a research task,
not a halt.

Two rules for that research:

1. **Marketing is not documentation.** "Comprehensive REST APIs" with no endpoint reference,
   auth scheme or request example is `confidence: unverified`. Say so in the report.
2. **Honour the negative guards in `packs/_UNVERIFIED.yml`.** Name collisions will otherwise
   produce a confident, entirely fictional pack. The known case: `docs.xdocm.com` documents a
   mortgage document system, not Bluestream XDocs.
