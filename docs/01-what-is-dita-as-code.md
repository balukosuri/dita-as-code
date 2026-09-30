# 1. What is DITA-as-code?

No commands in this page. It explains the idea, so the rest makes sense. If you already know what
docs-as-code is, skip to [Getting started](02-getting-started.md).

---

## The problem this solves

You write in DITA. Your documentation is probably in one of two places:

- **Files on your computer**, edited in Oxygen, Arbortext, XMetaL or FrameMaker
- **A system you log into**, like Heretto, MadCap IXIA, Tridion Docs, AEM Guides or Paligo

Either way, some of this is probably familiar:

- Publishing means someone runs a script, or clicks a button, on one particular machine
- If that person is away, nobody publishes
- A broken cross-reference is found by a reader, not by a tool
- Nobody can see what changed between last month's PDF and this month's
- The developers who know whether the content is *correct* never look at it
- Something works on one laptop and not another, and nobody knows why

None of that is a DITA problem. It is a **process** problem, and software teams solved it years ago.

## What docs-as-code means

Docs-as-code means using the same tools and habits for documentation that developers use for code:

- **The source lives in version control**, so every change is recorded, attributable and reversible
- **Changes are reviewed** before they go live
- **Checks run automatically** on every change
- **Publishing is automatic**, triggered by approving a change rather than by a person

That is the whole idea. Four habits.

## The myth: "docs-as-code means Markdown"

Almost every article about docs-as-code assumes you will write in Markdown. That has been repeated
so often that many people believe DITA and docs-as-code are opposites.

They are not. Markdown became associated with docs-as-code for historical reasons, not technical
ones. Nothing in those four habits requires a particular file format.

**DITA-as-code means getting all four habits while keeping DITA.**

## Why you would not want to leave DITA

If you already write DITA, you almost certainly depend on things Markdown cannot express:

- **Writing something once and using it in many places.** `conref` and `keyref` let you reuse a
  sentence, a paragraph or a whole topic. When it changes, it changes everywhere. Markdown has no
  equivalent without custom preprocessing.
- **One source, different outputs per audience.** Conditional attributes and `.ditaval` filters
  let one set of files produce different content for different readers, editions or formats.
- **Structure that is actually enforced.** A DITA task topic must contain steps. You cannot
  accidentally publish a procedure with no procedure in it.

If you have ever seen the same warning in fifteen places with four of them out of date, you
already know why these matter.

Migrating away from DITA to get docs-as-code would mean giving up the capabilities you chose DITA
for, to gain habits you can have anyway. That trade makes no sense, and DAC exists so you do not
have to make it.

## What DAC actually does

DAC looks at what you already have and builds the missing pipeline around it.

**It does not change how you write.** This is the single most important thing to understand.
Arbortext, XMetaL, Oxygen and FrameMaker are all desktop applications that cannot be driven from
a script — but they all save ordinary DITA files to disk. So DAC ignores your editor completely
and automates **everything that happens after you press save**.

You carry on writing exactly as you do today. What changes is that saving now leads somewhere.

## What you get

- **A history.** Every change recorded, with who made it and why.
- **Automatic checking.** Broken cross-references, invalid structure and style problems caught
  before publication rather than after.
- **Reviewable changes.** Colleagues see what actually changed, and can comment on it.
- **Automatic publishing.** Approving a change publishes it. No script, no particular laptop.
- **A build that works anywhere.** The same command on your machine and on the server.
- **Documentation for your team**, written for people who have never used any of this.

## What you will not get, honestly

- **If your content is in a CCMS**, subject-matter review stays in the CCMS. The version history
  gives you visibility into what changed, not a gate on it.
- **If your content is not really DITA** — MadCap Flare is XHTML, Author-it is a database,
  unstructured FrameMaker is binary — you get version control, automatic checks and automatic
  publishing, but not meaningful change-by-change diffs or DITA-style reuse. DAC will tell you
  this rather than pretend.
- **Some things cost money.** Where a capability needs a licence you do not have, DAC installs the
  best free alternative, tells you exactly what you are missing, and writes the request for the
  thing you would need to buy.

## Words you will see

| Word | What it means |
|---|---|
| **Git** | The system that records every change to your files. What "version control" means in practice. |
| **Repository** (or repo) | A folder whose history Git is tracking. |
| **Branch** | A private copy of the docs where unfinished work cannot affect anyone else. |
| **Commit** | One saved change, with a note about what it was. |
| **Pull request** (PR) | A proposed set of changes, shown for review before going live. Called a merge request on GitLab. |
| **CI** | Continuous integration. A server that automatically checks and builds every change. |
| **DITA-OT** | DITA Open Toolkit. The free program that turns DITA files into HTML, PDF and other outputs. |
| **ditaval** | A file listing which conditional content to include or exclude for a particular output. |
| **CCMS** | Component Content Management System. A server-based system for authoring DITA, like Heretto or IXIA. |

You do not need to memorise these. They are here so nothing in the other pages is a surprise.

## Is this genuinely possible, or aspirational?

It is genuinely possible, and it is already being done.

DITA Open Toolkit's own documentation is 267 DITA topics published through exactly this kind of
pipeline. The OASIS DITA specification itself is written in DITA and built by automated checks.
Tech Writer Koduje, the team who first argued this case publicly, run it in production and say
plainly: "we have done it and it works."

DAC was also tested against real documentation, not toy examples. Pointed at Couchbase Server's
documentation — 1,383 DITA topics that had been published for years using a hand-written shell
script — it built them successfully and then found **36 errors and 15 warnings** in that live
content, including a map file referenced by the root map that did not exist.

Which brings us to the most valuable thing in this whole toolkit.

## The one thing worth remembering

**A successful build does not mean the documentation is correct.**

On that Couchbase content, the ordinary build reported success and produced 794 pages. The strict
validation of the *same files with the same tool* failed. Both were true at once.

This is why DAC always sets up checking as a separate step from building, and why it treats a
"green" build as insufficient evidence on its own. It is also why teams can publish broken
cross-references for years without knowing.

---

Next: [Getting started](02-getting-started.md) — installing DAC and your first run.
