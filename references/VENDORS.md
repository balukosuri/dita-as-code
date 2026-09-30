# Vendors

Read this when a CCMS or delivery platform is detected, or when running
`dac vendors research <name>`. Per-vendor operational detail lives in `packs/*.yml`; this page
carries the cross-vendor conclusions and the research procedure.

All facts verified 18 September 2026.

---

## The finding that shapes every archetype B run

**No CCMS surveyed syncs DITA source to Git.** Not Heretto, MadCap IXIA, RWS Tridion Docs, AEM
Guides, Paligo, Componize or Bluestream XDocs.

What the marketing looks like versus what is actually true:

- **Paligo** advertises GitHub integration. It uploads **published output as a zip file**. There is
  no diffable source history.
- **AEM Guides** shipped a Git Connector in the 2026.08 cloud release. It runs **inbound only** -
  Git into AEM. Anyone reading the release-note headline gets the direction backwards.
- **Bluestream** publishes a paper titled *"How do you decide between Git or a Component Content
  Management System?"*, framing the two as alternatives rather than complements.

So the export bridge is always something DAC builds. That is the core value for these teams, and
no vendor will do it for them. Say so plainly in the audit rather than letting a writer discover it
after a procurement conversation.

---

## Capability summary

| Vendor | Source format | API | Admin needed? | Git | Programmatic export | Internal DITA-OT |
|---|---|---|---|---|---|---|
| Heretto | DITA | v2 publishing only (Alpha); v1 content API not public | admin to install toolkits | none | partial, v1 gated | 2.5.4 to 3.7.4 |
| MadCap IXIA | DITA | REST, read-only config, incomplete | sysadmin for Export | none | yes, raw DITA zip | 2.5.4 |
| RWS Tridion Docs | DITA | OpenAPI 3 + legacy WCF | service account | none | yes, via ISHRemote | not DITA-OT |
| AEM Guides | DITA | partial REST, 5 families | Adobe IMS OAuth | inbound only | partial | 3.3.2, PDF not DITA-OT |
| Paligo | **DocBook 5.1** | REST v2 | **admin, no exceptions** | output zip only | yes, lossy publish | none |
| Componize | DITA + DocBook | claimed, undocumented | unknown | none | CMIS is the real path | unpublished |
| Bluestream XDocs | DITA | marketing only | unknown | none | undocumented | unpublished |
| Author-it | proprietary DB | outbound only | n/a | none | UI export; AION JSON | none |
| MadCap Flare | **XHTML** | none | n/a | **native, first-class** | it is already files | none |
| Fluid Topics | ingests many | REST + `ftpub` CLI | `CONTENT_PUBLISHER` | none | delivery target | none |
| Zoomin | ingests many | **end of renewals** | n/a | n/a | n/a | n/a |

Authoring tools and render services are in their own packs. The short version on bundled toolkits:
**Oxygen 28.1 ships DITA-OT 4.4.0 and XMetaL 20.0 ships 4.2.2 XM**, both far newer than any cloud
CCMS above.

---

## Corrections to widely held assumptions

Ranked by how much damage believing the wrong thing causes.

**1. Arbortext Publishing Engine has no `f=compose`.** It occurs zero times in the 8.3.1
Programmer's Guide. The real functions are `f=acl`, `f=java`, `f=javascript`, `f=vbscript`,
`f=convert`, `f=init`, `f=status` and others; publishing goes out as
`f=java&class=com.arbortext.e3c.Application`. Access is governed by the `AllowedFunctions`
allowlist in `e3config.xml`, so valid credentials calling a non-allowlisted function still fail.

**2. Fluid Topics does not need `KHUB_ADMIN` to publish.** `CONTENT_PUBLISHER` is sufficient;
admin is needed only to *create* a source. Asking for admin requests far more privilege than the
job needs and is more likely to be refused.

**3. Heretto's content API is gated behind a person, not a permission.** The v1 endpoints are real
but documented "upon request" via a Customer Success Manager. The blocker is a CSM conversation,
not an admin key - and sending it to an administrator just gets it forwarded.

**4. Paligo is DocBook 5.1, not DITA.** Confirmed in Paligo's own marketing. Its DocBook publish is
also lossy: it "does not contain any metadata or information about text fragments and variables",
so reuse constructs are gone before you can convert them. `GET /documents/{id}` returns
higher-fidelity source.

**5. MadCap Flare has first-class native Git.** Git, Perforce, SVN and TFS are built in, branching
is supported in the UI for Git, and MadCap's own docs describe running GitFlow internally. Do not
imply Flare teams lack version control. What they lack is semantic diffs and component reuse -
and several archetype B CCMSs have a *worse* Git story than Flare does.

**6. AEM Guides' default PDF engine is not DITA-OT.** Native PDF, CSS-based, is the default in
current versions. So the version-drift conversation is not 3.3.2 against 4.4.1 - it is that a
completely different engine produces the output of record, and a local DITA-OT build can never
match it.

**7. XMetaL is not end-of-life.** Version 20.0 is current, with updated Windows SDK binaries and
security fixes, and an active maintenance agreement. It bundles the most modern toolkit of any
system in this survey apart from Oxygen.

**8. Zoomin is sunsetting.** Salesforce closed the acquisition in November 2024 and ended renewals
on 1 September 2025 for the portal, In-Product Help, the API and Headless. Detecting Zoomin is
detecting a contract running out.

**9. Oxygen Content Fusion is a Git-native DITA CMS**, not merely a review tool. Projects mirror a
Git repo with per-branch author workspaces and automatic review branches. For an Oxygen shop it is
the shortest existing path to docs-as-code - check for it before building a parallel pipeline.

**10. FrameMaker Publishing Server is about four years behind FrameMaker desktop**, and its REST
paths changed shape between releases. Probe the version before generating any URL.

**11. IXIA returns HTTP 200 on bad credentials**, with error code `-10021` in the body. Status-code
checking alone reports a false success.

**12. Nobody in this ecosystem ships an MCP server.** Not Heretto, Paligo, Oxygen, MadCap or Adobe.
The only prior art is DitaCraft's standalone server and two build-it-yourself community recipes.
Plan on being alone rather than composing with vendor servers.

---

## Separate SKUs worth naming

DAC must be able to say "you need to buy X", with a figure where one is public.

| Capability | Cost |
|---|---|
| Oxygen Scripting | quote only; trial keys from sales |
| Oxygen Publishing Engine | about $7,896, v28 4-core Professional with 1 year SMP |
| Oxygen WebHelp alone | about $5,026, v28 4-core |
| Oxygen PDF Chemistry alone | about $2,538 licence, $4,230 with SMP |
| FrameMaker Publishing Server | separate purchase from FrameMaker |
| Flare enterprise floating licence | required for unattended CI; quote only |
| Paligo Business | from $15,000/year; API needs Professional or above |
| Heretto Portal / Deploy API | separate products from the CCMS |
| IXIA API support | billed against monthly Customer Care hours |
| Author-it AION | **free in every subscription** |

The Oxygen trap worth flagging early: Scripting, Publishing Engine, WebHelp and PDF Chemistry are
**four separate purchases with four separate licence keys in four locations**. Teams routinely
discover this mid-project.

---

## Researching an unknown vendor

`dac vendors research <name>` runs during a one-shot run automatically. An unrecognised tool is a
research task, not a halt.

Procedure:

1. **Find the official documentation domain.** Not a blog, not a reseller, not a comparison site.
2. **Answer the operational questions in order.** Native source format. Is there a documented REST
   API, with a base URL and auth scheme. What minimum role does it need. Is there a CLI. Is there
   Git integration, and is it source sync, output only, or inbound only. Can a full source export
   be triggered programmatically, and in what format. Does it run DITA-OT internally, and is the
   version knowable.
3. **Classify the archetype** from the answers, using `ARCHETYPES.md`.
4. **Write the pack** to `.dac/packs/<id>.yml` using the schema in `packs/_SCHEMA.md`.
5. **Mark everything `confidence: unverified`** until a live probe confirms it.

Three rules that keep this honest:

**Marketing is not documentation.** "Comprehensive RESTful APIs" with no endpoint reference, no
base URL and no auth scheme is `confidence: unverified`. Record the claim and the absence of
evidence, and say so in the report.

**Honour the negative guards.** Name collisions will otherwise produce a confident, entirely
fictional pack. The known case: searching for the Bluestream XDocs API surfaces `docs.xdocm.com`,
which documents an unrelated mortgage document system. See `packs/_UNVERIFIED.yml`.

**Check whether the product still exists.** Two of the vendors in the original brief had changed
materially - Zoomin is winding down and Vasont is now GlobalLink CCMS. Verify current status before
recommending an integration.

---

## Vendors confirmed to exist but not researched

Good candidates for `dac vendors research`: GlobalLink CCMS (formerly Vasont Inspire), Astoria,
DiscoverCX, DITAToo, DITAworks, DX4, RSuite, Sirius DITA, Tektur, Xeditor, SCHEMA ST4, Docufy
Cosima, Documoto.

Naming corrections for the pack database: **Jorsek** is the former name of Heretto, not a separate
vendor. **Vasont** is now GlobalLink CCMS. **DCL** is a content-conversion services firm, not a
CCMS, and belongs in a migration-partners list.
