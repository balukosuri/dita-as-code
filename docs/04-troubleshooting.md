# 4. Troubleshooting

Every problem below was actually encountered while building and testing DAC against real
documentation. Find your message, read the cause, apply the fix.

**Start here:** `dac doctor` re-checks your environment and shows what changed since the last run.
Most "it worked yesterday" problems are answered by that one command.

---

## Nothing found

### "No content found in this folder"

**Not an error.** The most common first-run outcome, and DAC deliberately refuses to invent a
score for an empty folder.

Four causes, in order of likelihood:

1. **Your content is in a CCMS.** There is genuinely nothing on your computer. Run
   `dac connect --source "https://yourcompany.heretto.com"` (or whatever address you log into).
2. **You are in the wrong folder.** Look for the one containing `.ditamap` files. Your editor's
   recent-projects list is the fastest way to find it.
3. **Content is on a network share.** Copy it locally first.
4. **It is in a repository you have not cloned.** `dac connect --source <url> --clone`.

### DAC found my editor but says there is no content

Correct behaviour, and a bug that was deliberately fixed. Having Oxygen or DITA-OT installed says
nothing about whether *this folder* contains anything. The report separates "tooling on this
machine" from "content found here" for exactly this reason.

### "DAC does not recognise <hostname>"

You gave `connect` an address it has no capability pack for.

- If it is a Git repository, add `.git` to the URL or pass `--kind git`
- If it is a CCMS DAC has not seen, run `dac vendors research <hostname>`
- If it is your published documentation site, DAC needs the **source**, not the output

DAC will not guess at a vendor's capabilities. An invented integration is worse than none.

---

## Build and environment

### "Unable to locate a Java Runtime" / no build path

DITA-OT needs Java. So does prose linting, because Vale drives the `dita` command internally.

```bash
# macOS
brew install --cask temurin@17

# Windows
winget install EclipseAdoptium.Temurin.17.JDK
```

**Install Java 17 specifically, not "the latest Java."** DITA-OT 4.4.x is built and tested against
17, and its own CI pins exactly that.

**Do not run a bare `brew install dita-ot`.** The formula depends on plain `openjdk`, which
currently resolves to a JDK far newer than the toolkit is tested against. You get DITA-OT and a
Java problem in one command.

No Java and cannot install it? Use Docker:

```bash
DAC_USE_DOCKER=1 ./scripts/build.sh
```

### Docker is installed but builds still fail

The client is present but the daemon is not running — a genuinely confusing state, and DAC reports
it distinctly. Start Docker Desktop (or your container runtime) and try again.

```bash
docker info    # errors if the daemon is down
```

### Builds pull the wrong container image

Use `ghcr.io/dita-ot/dita-ot`. **Never `ditaot/dita-ot` on Docker Hub** — abandoned years ago,
newest tag 2.5.3, and its own README warns it will not work. It ranks highly in search results,
which is how people end up there.

### "DOTA069F: The input resource cannot be located"

A path in `config/dita-ot-project.xml` is wrong. Almost always the `../` frame.

**Paths inside the project file are relative to the project file's own directory, not the
repository root.** With the project file in `config/`, a map at the root is `../your.ditamap`.

The classic mistake is a doubled prefix — `../../your.ditamap` — which resolves to a directory
*above* your repository and reads as a missing file rather than a path bug. If the error path
looks one level too high, that is it.

The one exception: `output/@href` resolves against the output directory given on the command line,
not against the project file.

### "element 'profile' not allowed here"

A schema error in the project file. A `<context>` referenced by `idref` accepts the `idref`
attribute **only** and cannot have children — so `<profile>` belongs inside `<publication>`, after
any `<param>` elements.

Validate it properly:

```bash
jing -c "$DITA_HOME/resources/project.rnc" config/dita-ot-project.xml
```

Use **jing**, not `xmllint`. xmllint is not a dependable RELAX NG validator, which matters
because this schema is RELAX NG.

### Validation fails or is extremely slow

Set the XML catalog:

```bash
export XML_CATALOG_FILES="$DITA_HOME/catalog-dita.xml"
```

DITA files refer to their grammar by public identifier, not file path. Without a catalog,
validation either fails outright or **silently downloads DTDs over the internet** — slow,
different results on different days, and completely broken offline.

### Gradle builds fail with a network error

Your company probably proxies or blocks Maven Central. `dac doctor` distinguishes three states:
reachable, proxied-and-working, and policy-denied.

If denied, either point the build at your internal artifact proxy or skip Gradle entirely — DAC
prefers the plain DITA-OT command-line path for exactly this reason.

Be aware that such proxies often allow most paths while denying specific artifacts, so a passing
probe does not guarantee every dependency resolves.

---

## Content errors

These are found in *your documentation*, not in DAC. Finding them is the point.

### DOTX008E — "The resource cannot be loaded"

A referenced file does not exist. Usually something was renamed or moved.

This is common in real estates. Couchbase's root map referenced `introduction.ditamap`, which was
not in the repository at all, and their published pipeline never mentioned it.

### DOTJ046E — "@conkeyref cannot be resolved"

A reuse key is not defined, so **reused content is silently missing from the published page**.
Check that the key is defined in a map that is actually in scope.

### DOTX031E — "resource is not available to resolve link information"

A link target cannot be reached, so link text and titles cannot be generated.

### DOTJ041E / DOTX010E — conref problems

Malformed `@conref` syntax, or a target that does not exist.

### The build succeeds but validation fails

**This is normal, expected, and the most important thing DAC does.**

```
lenient build exit code : 0    ← success
strict validate exit code : 1  ← failure
```

Same files, same tool. A DITA build in default mode tolerates things that strict validation
rejects, so a build passing tells you nothing about whether the content is correct. This is
exactly how a team publishes broken cross-references for years.

Fix the content. Do not relax the validation to make it quiet.

### Content appears in the wrong output

Your `.ditaval` filter is not being applied. Check that every deliverable in
`config/dita-ot-project.xml` names its filter.

**Take this one seriously.** A build without its filter *succeeds* and publishes the wrong
content. In testing, a paragraph marked `audience="internal"` appeared in published HTML with a
zero exit code. If your PDF contains web-only content, or internal notes reach customers, this is
why.

### My link check passes but links are broken

Are you on AEM Guides with a UUID build? References are UUID-based and path-independent, so a
filename-based link checker **passes clean on genuinely broken links**. You need a UUID-aware
check.

### Everything broke after I renamed a topic

Renaming a DITA file breaks every reference to it, with no warning at edit time.

```bash
git checkout -- path/to/file.dita    # undo it
```

Then rename using your editor's refactoring command — Oxygen updates all references for you.
**Never rename DITA files with `mv` or in Finder.**

---

## Checks and tooling

### Vale finds nothing, or reports odd errors

Three hard constraints:

1. **Vale needs DITA-OT on `PATH`.** It works by running `dita` internally and linting the
   resulting HTML. No Java means no prose linting of DITA at all.
2. **`.ditamap` is not supported.** Prose held in maps — short descriptions, navigation titles —
   is **not covered**. Read those yourself; do not assume coverage you do not have.
3. **Never add a `[formats]` section mapping `dita`.** It silently breaks native DITA handling.
   Keep the config scoped to `[*.dita]`.

Seeing "No XSLT transform provided!"? A bare `[*.xml]` section without a `Transform` causes that
for every stray XML file. Remove it.

### Vale ignore patterns do nothing

You are below version 3.22.0. `TokenIgnores` and `BlockIgnores` only work on DITA from that
version onward, so below it a misfiring rule has to be switched off entirely rather than silenced
in one place.

```bash
brew upgrade vale
```

### Prose linting looks like it has hung

It probably has not. Vale invokes `dita` per run and its own documentation warns of worse
performance on DITA than other formats. On several hundred topics this is slow. Let it finish.

### Schematron checks are skipped

Install a runner and point at it:

```bash
export SCHXSLT_JAR=/path/to/schxslt-cli.jar
```

Note `xmllint --schematron` implements only a subset of ISO Schematron and is unreliable for
abstract patterns and phases. Use SchXslt.

If Maven Central is blocked, get the jar from the project's own release page instead.

---

## Git and review

### XML diffs are unreadable in pull requests

The formatter is not installed or not running.

```bash
npm ci
npm run format
```

Deterministic XML formatting is what makes DITA review viable. Without it, every change looks
enormous and reviewers quietly stop reviewing. This is the single highest-value fix available.

### The pre-commit hook rejects my commit

It is doing its job — malformed XML, or unformatted files. Run `npm run format` and commit again.

Genuine emergency escape hatch:

```bash
git commit --no-verify
```

Use it rarely. CI will still catch the problem.

### CI runs twice on every change

DAC wrote a workflow alongside one that already existed. Delete the duplicate. DAC's own rule is
"adopt, don't impose" — if it got this wrong, the existing pipeline was in an unusual location.

### My existing format check started failing

DAC reformatted source that your existing check measures differently. Either adopt DAC's Prettier
configuration as the single source of truth, or revert the formatting commit — it is deliberately
kept as a separate commit so it can be dropped cleanly.

---

## Vendor-specific

### Heretto: I cannot get content out

Expected. The v2 API is publishing-only and self-labelled Alpha. The v1 endpoints that read
content are real but their documentation is only available on request.

**Ask your Customer Success Manager, not an administrator.** This is a documentation and
configuration request; an admin cannot help and will forward it. Ask for the v1 API documentation
and for webhooks in NotifyPull mode.

Do not build on WebDAV. Heretto states twice that it does not provide general WebDAV support.

### Heretto or IXIA: it builds in the CCMS but not locally

Version drift, and it is rarely diagnosed. Heretto's cloud toolkit caps at 3.7.4, IXIA defaults to
**2.5.4** — roughly nine years behind current 4.4.1. Output genuinely differs.

```bash
dac doctor    # compares every DITA-OT version in play
```

### IXIA: my credentials work but nothing happens

IXIA returns **HTTP 200 with error code `-10021`** on bad credentials. Anything checking only the
status code reports a false success. Parse the `error` field in the response body.

### Paligo: the API rejects my key

Paligo requires an **admin** user, with no exceptions, and licence permissions carry into the API.
A non-admin key cannot be made to work. This is a hard wall, not something to work around.

Also: Paligo content is **DocBook 5.1, not DITA**. If you are trying to run a DITA pipeline over
it, that is the real problem.

### AEM Guides: my PDF does not match the published one

It never will. AEM Guides defaults to a CSS-based Native PDF engine, **not DITA-OT**. A different
program produces the output of record. Decide which one is authoritative before automating.

### Arbortext: Publishing Engine rejects my call

Access is governed by the `AllowedFunctions` allowlist in `e3config.xml`, not by credentials.
Valid credentials calling a non-allowlisted function still fail. Ask the PE administrator which
patterns are permitted.

And if you are looking for `f=compose` — it does not exist. Publishing goes out as
`f=java&class=com.arbortext.e3c.Application`.

### Flare: CI builds fail with a licence error

Flare deactivates itself when a virtual machine's hardware fingerprint changes, so ephemeral cloud
runners fail even though Flare was activated yesterday.

`madbuild -activate` fixes it, **but only on enterprise floating licences**, and needs a
`license.json` in the Flare Desktop application folder. Otherwise use a pinned, non-ephemeral
Windows runner.

Also add an antivirus exclusion for the `Output` folder — scanning it mid-build is a documented
cause of failures.

### My published output uses a custom format that DAC did not set up

DAC found a custom transtype in your build but no plugin in the repository. Stock output will not
look like your site.

Vendor the plugin into the repository, or install it in CI by pinned zip, then change the
transtype in `config/dita-ot-project.xml`.

---

## DAC itself

### "detect.json is corrupt and cannot be read"

A previous run was interrupted.

```bash
rm -rf .dac/state && dac audit
```

### "detection results not found"

Run the audit first. Later stages read what detection wrote.

### I want to undo everything DAC did

```bash
git checkout main            # or master
git branch -D dac/setup
```

That is all of it. Everything lands on that branch by design.

### The report says a score I disagree with

Read the per-axis evidence — each score lists why it was given. If the evidence is wrong, the
detection is wrong, and that is worth reporting. If the evidence is right but the conclusion feels
harsh, check the **ceiling**: it may be an honest limit of your tooling rather than a judgement.

### It claims a capability I do not have

Check the capability pack in `packs/` for `confidence: unverified`. That marker means a vendor
advertises something no public documentation confirms. DAC should say so in the report — if it
asserted it instead, that is a bug worth reporting.

---

## Still stuck?

1. `dac doctor` — what changed since last time
2. `dac state` — a compact summary of what DAC currently believes
3. `.dac/journal.jsonl` — every action taken, in order
4. **Ask your AI assistant.** Your repository has an `AGENTS.md` describing its layout, so Cursor
   or Claude Code can read an error alongside the structure and explain it. Paste the error and ask.
