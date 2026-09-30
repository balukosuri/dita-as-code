# Setup: getting a machine ready

You only do this once per machine. If you are already set up and just want the daily loop, read
`RUNBOOK.md` instead.

**You do not need to install a new authoring tool.** Keep using {{EDITOR_NAME}}. What you are
installing here is the machinery that checks and publishes what you write.

---

## The fast path: a devcontainer

If you have Docker and VS Code or Cursor, this is one click and you can skip the rest of the page.

1. Open this folder in VS Code or Cursor.
2. When it offers to "Reopen in Container", accept.
3. Wait a few minutes for the first build.

You now have Java 17, DITA-OT {{DITA_OT_VERSION}}, Vale, and XML validation, all at the exact
versions CI uses. That last part matters: when your machine and CI run the same image, "it works on
my machine" stops being a conversation.

Confirm it worked:

```bash
./scripts/validate.sh
```

---

## The manual path

Install these four things in order. The order matters, because each depends on the one before.

### 1. Java 17

**Install Temurin 17 specifically, not "the latest Java".**

```bash
# macOS
brew install --cask temurin@17

# Windows (winget)
winget install EclipseAdoptium.Temurin.17.JDK

# Debian/Ubuntu
sudo apt install temurin-17-jdk
```

Check it:

```bash
java -version    # should report 17.x
```

**Why version 17 and not something newer:** DITA-OT {{DITA_OT_VERSION}} is built and tested
against Java 17, and DITA-OT's own CI pins exactly this. Newer JDKs sometimes work and sometimes
fail with errors that point at internal build machinery rather than the real cause, which is a
miserable afternoon.

### 2. DITA-OT {{DITA_OT_VERSION}}

Download the release zip and unpack it somewhere permanent:

```bash
curl -L -o dita-ot.zip \
  https://github.com/dita-ot/dita-ot/releases/download/{{DITA_OT_VERSION}}/dita-ot-{{DITA_OT_VERSION}}.zip
unzip dita-ot.zip
```

Then add its `bin` directory to your `PATH` and set two environment variables. In
`~/.zshrc` or `~/.bashrc`:

```bash
export DITA_HOME="/path/to/dita-ot-{{DITA_OT_VERSION}}"
export PATH="$DITA_HOME/bin:$PATH"
export XML_CATALOG_FILES="$DITA_HOME/catalog-dita.xml"
```

Check it:

```bash
dita --version   # should report {{DITA_OT_VERSION}}
```

**Two warnings that will save you time:**

**Do not run a bare `brew install dita-ot`.** The Homebrew formula depends on plain `openjdk`,
which currently resolves to a JDK far newer than the toolkit is tested against. You get DITA-OT and
a Java problem in one command.

**`XML_CATALOG_FILES` is not optional.** DITA files refer to their grammar by public identifier,
like `-//OASIS//DTD DITA Map//EN`, rather than by file path. Without the catalog, validation either
fails outright or silently downloads DTDs over the internet - which is slow, gives different
results on different days, and fails completely offline.

### 3. Node 20 or later

```bash
# macOS
brew install node

# Windows
winget install OpenJS.NodeJS.LTS
```

Then install this project's tooling:

```bash
npm ci
```

This gives you the XML formatter and the pre-commit hook.

**Why a documentation project needs Node:** it is only for the formatter. That formatter is what
makes your XML diffs readable in code review, which is the difference between review that works
and review that everyone quietly stops doing.

### 4. Vale 3.22.0 or later

```bash
brew install vale        # macOS
winget install --id errata-ai.Vale
```

**3.22.0 is a floor, not a preference.** Below that version, Vale's ignore patterns do not work on
DITA, which means a rule that misfires on one topic has to be switched off for the whole project
rather than silenced in one place.

Note that Vale lints DITA by running DITA-OT internally, so step 1 and step 2 have to be done
first. This is why the order matters.

---

## Optional: editor validation in VS Code or Cursor

If you want validation while you type in VS Code or Cursor - **in addition to**, not instead of,
{{EDITOR_NAME}} - install the Red Hat XML extension. `.vscode/settings.json` is already configured
for it.

```
code --install-extension redhat.vscode-xml
```

**An honest note about DITA in VS Code.** The Red Hat XML extension is excellent at validation and
navigation, and is very widely used. But there is no rich DITA *authoring* experience in VS Code.
The one purpose-built DITA extension, DitaCraft, has roughly 1,200 installs and a single
maintainer - it does real work, including map visualisation and key-resolution tracing, but it is a
small project and you should know that before depending on it.

Write in {{EDITOR_NAME}}. Use VS Code or Cursor for Git, for the build, and for asking your AI
assistant about the repository.

---

## Confirming everything works

```bash
./scripts/validate.sh
./scripts/build.sh
```

Then open `out/` and look at the output. If you can see published documentation, you are done.

If `validate.sh` reports that it is skipping checks, it will name which tool is missing. Come back
to that step.

---

## Nothing is installed and I cannot install anything

This is a normal situation, not a blocker.

You can still contribute. Write in {{EDITOR_NAME}}, commit, and push. CI validates and builds
everything on every pull request, so your work gets checked either way. You just will not be able
to see the result before you push it.

If you want a local build without installing Java, and you have Docker:

```bash
DAC_USE_DOCKER=1 ./scripts/build.sh
```

---

## Keeping versions aligned

Three places have to agree on the DITA-OT version, or output differs between them:

- Your machine, from step 2
- CI, in `.github/workflows/`
- {{EDITOR_NAME}}, which bundles its own copy

Check all three at once:

```bash
dac doctor
```

{{CCMS_VERSION_NOTE}}
