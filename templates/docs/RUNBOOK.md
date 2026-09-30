# Runbook: your day-to-day loop

This is what working on the docs looks like now. If you only read one page, read this one.

**The most important thing to know: you keep writing exactly where you write today.** Nothing in
this setup changes your authoring tool. Everything here happens *after* you save.

---

## The loop

```
1. Get the latest changes
2. Start a branch
3. Write in your editor, as always
4. Check your work
5. Send it for review
6. Merge
```

Steps 1, 2, 5 and 6 are new. Step 3 is unchanged. Step 4 used to happen in review, or not at all.

---

## 1. Get the latest changes

```bash
git checkout {{DEFAULT_BRANCH}}
git pull
```

**If you have never used Git:** `pull` means "download what other people changed". Do this before
you start writing, every time. It is the single habit that prevents most conflicts.

Your editor may have a Git panel that does this with a button. Oxygen has a built-in Git client;
VS Code and Cursor have a Source Control panel. Use whichever you prefer - they do the same thing.

## 2. Start a branch

```bash
git checkout -b your-name/what-you-are-changing
```

A branch is a private copy of the docs where your unfinished work cannot affect anyone else. Name
it after what you are doing, for example `priya/install-guide-rewrite`.

**Why bother:** it means you can leave work half-finished without breaking the published docs, and
it means your changes get reviewed as one coherent set rather than trickling in.

## 3. Write, in your editor

Open the project in {{EDITOR_NAME}} and work exactly as you always have. Create topics, edit them,
add them to maps, use conrefs and keyrefs.

Nothing about this step has changed, and nothing about it should. This setup deliberately does not
touch your authoring tool.

## 4. Check your work

```bash
./scripts/validate.sh
```

This runs four checks: is the XML legal, does it match the DITA grammar, do your conrefs, keyrefs
and links actually resolve, and does it follow the house rules.

To see the actual output:

```bash
./scripts/build.sh          # every deliverable
./scripts/build.sh html     # just one
./scripts/build.sh --list   # what deliverables exist
```

Output lands in `out/`.

**A few things worth knowing:**

- **The first build is slow.** Later builds are faster.
- **Prose linting on DITA is genuinely slow.** It works by converting each topic to HTML and
  linting that. On a few hundred topics it can look like it has hung. It has not.
- **Map files are not prose-linted.** Short descriptions and navigation titles held in
  `.ditamap` files are not covered. Read those yourself.
- If `validate.sh` says it is skipping checks, see `SETUP.md` - something is not installed.

## 5. Send it for review

```bash
git add .
git commit -m "Rewrite the install guide for the 5.0 release"
git push -u origin your-name/what-you-are-changing
```

Then open a pull request. The command line will print a link, or use the button in your editor's
Git panel.

**What happens automatically:** validation runs, the docs build, and the checks report back on the
pull request. If something is wrong, you will see it there before a human spends time on it.

**Why your diffs are readable.** XML diffs are usually miserable to review. This repository runs a
formatter on every commit so that the XML is laid out identically no matter who wrote it. That
means a diff shows what you actually changed, not a reshuffle of attributes and whitespace. This
is why reviewing DITA in a pull request works here when it often does not elsewhere.

**Commit messages:** say what changed and why, in a sentence. "Fix typo" tells a future reader
nothing; "Correct the port number in the install guide, was 8080, should be 8443" tells them
everything.

## 6. Merge

Once someone approves and the checks pass, merge the pull request. Publishing happens
automatically.

---

## When things go wrong

### The build fails and I do not understand the error

DITA-OT error codes are searchable and specific. The four worth recognising:

| Code | Meaning |
|---|---|
| `DOTJ041E` | A `@conref` is malformed |
| `DOTJ046E` | A `@conkeyref` cannot be resolved - usually a missing key definition |
| `DOTX010E` | A `@conref` points at something that does not exist |
| `DOTX028E` | A link has no valid target |

All four mean the same class of problem: something points at something that is not there. Usually a
file was renamed or moved.

**You can also just ask your AI IDE.** This repository has an `AGENTS.md` explaining its layout,
so Cursor, Claude Code or Copilot can read the error alongside the structure and tell you what
broke. Paste the error and ask.

### It builds fine for me but fails in CI, or the other way round

Almost always a version difference. Check that the DITA-OT version in
`.github/workflows/` matches the one in `.dac/config.yml` and the one your editor bundles.

**If you also use a CCMS, this is extremely common and rarely diagnosed.** Cloud CCMS toolkits run
well behind current DITA-OT - Heretto caps at 3.7.4, MadCap IXIA defaults to 2.5.4, AEM Guides
ships 3.3.2, against a current release of 4.4.1. Output genuinely differs between them. Run
`dac doctor` to compare the versions.

### I renamed a topic and everything broke

Renaming or moving a DITA file breaks every reference to it. Undo it, then do the rename using your
editor's refactoring command - Oxygen updates all references for you. Never rename DITA files with
`mv` or in Finder.

### Content is appearing in the wrong output

Check the `.ditaval` filters. Every deliverable in `config/dita-ot-project.xml` names the filter
that applies to it.

**This is the failure mode to take most seriously**, because a build with the wrong filter
succeeds. It does not warn you. It just publishes the wrong content. If the PDF contains content
meant only for the web, this is why.

### A check is blocking my merge and I think it is wrong

Say so in the pull request rather than working around it. If a rule misfires often, it is a bad
rule and should be changed in `config/schematron/house-rules.sch`. A rule nobody believes in gets
disabled, and then all of them do.

### Git says I have a conflict

Someone changed the same lines you did. Ask for help the first few times - it is a normal part of
working this way, not a sign you did something wrong. Your editor's merge tool will show both
versions side by side.

---

## What runs automatically, and when

| When | What happens |
|---|---|
| You commit | XML is reformatted; malformed XML is rejected |
| You open a pull request | Grammar validation, link and reference checks, prose linting, full build |
| You merge | Docs build and publish |
{{CCMS_ROW}}

---

## Commands worth remembering

```bash
./scripts/validate.sh       # check before pushing
./scripts/build.sh          # build everything
./scripts/build.sh --list   # list deliverables
npm run format              # reformat all XML
git pull                    # get others' changes
```

Everything else you can look up, or ask your AI IDE about.
