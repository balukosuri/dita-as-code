# Contributing to the documentation

For writers, developers, and anyone reviewing a documentation change.

---

## For technical writers

Read `RUNBOOK.md`. That is your page. Short version: pull, branch, write in {{EDITOR_NAME}} as
usual, run `./scripts/validate.sh`, push, open a pull request.

---

## For developers

The documentation is DITA XML rather than Markdown. Before you groan, here is why, and here is how
to contribute without learning DITA.

### Why this is not Markdown

Three capabilities the team depends on that Markdown cannot express without custom preprocessing:

- **Element-level reuse.** A single sentence or paragraph can be written once and pulled into
  dozens of topics. When it changes, it changes everywhere. `{{CONREF_COUNT}}` files here rely on
  this today.
- **Conditional content.** One source produces different output per audience, product edition or
  format, driven by attributes rather than by duplicated files.
- **Structural validation.** A task topic is checked to actually contain steps. You cannot merge a
  procedure with no procedure in it.

If you have ever seen documentation where the same warning appears in fifteen places and four of
them are out of date, that is the problem this solves.

### Contributing without writing XML

You have three options, in increasing order of effort.

**Option 1: file an issue.** Describe what is wrong or missing. Entirely valid, and often the most
useful thing you can do.

**Option 2: edit existing prose.** Find the `.dita` file, change the words between the tags, leave
the tags alone. It is XML, so it is more verbose than Markdown, but editing a sentence inside
`<p>...</p>` needs no DITA knowledge at all.

**Option 3: write Markdown.** DITA-OT accepts Markdown topics in a DITA map, so you can add a `.md`
file and a writer will wire it in.

**One thing that trips everyone up:** the file extension is ignored. A `.md` file must be
referenced with an explicit `format` attribute or the build does not see it at all:

```xml
<topicref href="your-topic.md" format="markdown"/>
```

Without `format="markdown"`, nothing happens. No error, no warning - the file is simply not part
of the build.

**What you give up by writing Markdown:** you cannot define reuse keys, conditional attributes, or
any of the semantics above. Markdown contributions are best treated as raw material that a writer
later enriches. That is a perfectly good workflow - it is faster for you and the writer keeps the
structure coherent.

### Reviewing a documentation pull request

You can read these diffs. The XML is auto-formatted on every commit specifically so that a diff
shows the actual change rather than a reshuffle of whitespace.

What to look for:

- **Is it true?** You know the product. This is the review only you can do.
- **Does the example work?** Copy the command and run it.
- **Are the version numbers right?**

What to ignore:

- Structure, tagging and style. Automated checks cover those, and the writers own them.

---

## Rules for everyone

### Never rename or move a DITA file with `mv`

Renaming breaks every reference pointing at it. Use your editor's refactor command - Oxygen updates
all references automatically. If you have already done it and things are broken, `git checkout` the
file and start again.

### Never commit build output

`out/`, `temp/` and `.gradle/` are ignored. If you see build output in a diff, something is
misconfigured - say so.

### Do not disable a check to get a merge through

If a check is wrong, fix the check. `config/schematron/house-rules.sch` holds the house rules and
is meant to be edited. A rule nobody believes in gets disabled, and once one goes, they all go.

### Keep pull requests small

One topic, or one coherent set of topics. A 60-file pull request does not get reviewed; it gets
approved without being read, which is worse than no review at all.

---

## What runs on your pull request

| Check | What it catches |
|---|---|
| Formatting | XML laid out inconsistently, so diffs stay readable |
| Grammar validation | Invalid DITA structure |
| Reference check | Broken conrefs, keyrefs and links |
| Prose linting | Style and terminology, on `.dita` files only |
| Build | Anything that breaks publishing |

Two honest caveats about what is *not* covered:

- **Prose linting does not cover `.ditamap` files.** Short descriptions and navigation titles held
  in maps are unchecked. Read those yourself.
- **A green build does not guarantee every reference resolved.** DITA-OT has historically been
  silent about some unresolved references, which is why there is a separate reference check. If
  published output looks wrong in a way the build did not catch, that is worth reporting.

---

## Getting help

Ask in {{HELP_CHANNEL}}.

You can also ask your AI IDE. This repository includes an `AGENTS.md` describing its layout, so
Cursor, Claude Code and Copilot can answer questions about where things live and what an error
means. Paste the error and ask.
