# 2. Getting started

Your first run, start to finish. Nothing here changes your documentation.

If you have not read [What is DITA-as-code](01-what-is-dita-as-code.md), five minutes there will
make this page much easier.

---

## Before you start

You need:

- **Cursor, Claude Code or GitHub Copilot.** DAC is an agent skill; it runs inside one of these.
- **Python 3.8 or later.** Already on macOS and Linux. Check with `python3 --version`.

That is all, to *look*. Setting things up later also wants Java 17 and DITA-OT, but DAC tells you
when and walks you through it. Do not install anything yet.

You do **not** need: administrator rights, a paid licence, any Git experience, or permission from
anyone. The audit reads and reports. It changes nothing.

## Step 1: Install DAC

```bash
git clone <this-repository>
cd <this-repository>
./dita-as-code/install.sh
```

You should see:

```
linked: ~/.cursor/skills/dita-as-code -> ...
  scripts   ok
  packs     ok (15 vendor packs)
  templates ok
  refs      ok

Self-test:
22 passed, 0 failed, of 22
```

Restart Cursor or Claude Code so it notices the new skill.

The installer uses symlinks rather than copies deliberately. A copy would freeze at today's
version and quietly stop picking up corrections — and vendor APIs change often enough that this
matters.

## Step 2: Find your content

This is the step people get stuck on, so it gets its own page: **[where is my content?](#where-is-my-content)**
below. Read the case that matches you before continuing.

## Step 3: Run the audit

In Cursor or Claude Code, say:

```
dita as code
```

Or run it directly, without an agent:

```bash
python3 dita-as-code/scripts/dac.py audit --root /path/to/your/docs
```

It takes a few seconds. On the largest repository tested — 257 MB, 1,383 topics — it took eight.

## Step 4: Read the report

You get `dac-audit.md` in your folder. It has five parts:

1. **The bottom line** — one paragraph: where you are, and the single thing most worth fixing
2. **What you have** — every system found, and the evidence for each, so you can check it
3. **What your situation means** — what is realistically achievable for your setup
4. **Where you stand** — ten areas scored, with an honest ceiling for each
5. **What happens next** — prioritised actions

### Reading the scores

```
| Area                    | Score | |        Status                  |
| Source extractability   | 4/4   | `####` | automatically, enforced |
| Automated build         | 0/4   | `....` | Not happening at all    |
| Review workflow         | 2/4   | `##--` | There is a script       |
```

- `#` is where you are
- `-` is reachable with your current tools
- `.` is **out of reach** with your current tools, and the report explains why

That last distinction matters. A ceiling below 4 is not a failure — it is an honest limit, and the
report tells you which tool sets it.

### Real examples

Three real repositories, to calibrate what a score means:

| Repository | Score | The binding constraint |
|---|---|---|
| A bare DITA content repo, no tooling | **23/40 (58%)** | Automated build — nothing runs |
| Couchbase Server docs, 1,383 topics, published by shell script | **23/40 (58%)** | Automated build |
| DITA-OT's own docs, full pipeline already | **35/40 (88%)** | Onboarding — no devcontainer |

After setup, Couchbase went from 58% to **95%**.

## Step 5: Decide whether to set anything up

The audit changes nothing. If you want DAC to build the pipeline:

```
dac setup
```

What that means in practice:

- **Everything lands on a branch called `dac/setup`.** Your main branch is untouched.
- **You can throw it all away with one command:** `git branch -D dac/setup`.
- It runs unattended for 10 to 20 minutes. You do not need to watch.
- It stops for nothing. Anything needing another person becomes a written request you can send.

Afterwards you get `dac-report.md`: what works, what was degraded and why, what is blocked, and
three things to do on Monday.

---

## Where is my content?

DAC runs on your computer. It does not connect to your editor. So the first question is where the
files actually are.

### Case 1: You write in Oxygen, Arbortext, XMetaL or structured FrameMaker

Your content is already a folder on your computer. **Open that folder in Cursor** and run the
audit. Nothing to clone, nothing to move.

Not sure which folder? Your editor's list of recently opened projects will tell you. You are
looking for the folder containing `.ditamap` and `.dita` files.

### Case 2: Your content is on a network drive or SharePoint

**Copy it to your own computer first**, then open the copy.

```bash
cp -R "/Volumes/Shared/Documentation" ~/docs-local
```

Git is slow and unreliable on a network share, and an interrupted operation on one can be
genuinely hard to recover from. This is worth doing properly.

### Case 3: You write in a CCMS

Heretto, MadCap IXIA, Tridion Docs, AEM Guides, Paligo and similar.

**There is nothing on your computer to open, and that is not a mistake on your part.** Your
content is on their server.

Make an empty folder, open it in Cursor, and run the audit anyway. DAC will find nothing,
recognise that this almost always means a CCMS, and ask which one. It then sets up a scheduled
export that copies your content down automatically.

Or tell it directly:

```bash
python3 dita-as-code/scripts/dac.py connect --source "https://yourcompany.heretto.com"
```

It identifies the system from the address and tells you exactly what it needs, **who to ask for it
by role**, and the honest caveat for that vendor.

One thing to know up front so it is not a surprise: **no CCMS on the market synchronises DITA
source to Git.** Not one. Paligo's much-advertised GitHub integration uploads published output as
a zip file. AEM's Git Connector runs the *other* way. So this export bridge is something DAC
builds for you. It runs one way, out of the CCMS only — **nothing is ever written back**, and you
keep authoring exactly where you do today.

### Case 4: Your docs are in a Git repository you have never copied down

```bash
python3 dita-as-code/scripts/dac.py connect \
  --source "https://github.com/yourcompany/docs.git" --clone
```

Then audit the folder it creates.

If you do not have the URL, ask whoever set up your team's repository. It is a one-off.

### Case 5: You are not sure

Paste whatever you have — a link, an address, a path — and let DAC work it out:

```bash
python3 dita-as-code/scripts/dac.py connect --source "<whatever you have>"
```

It recognises Git remotes, twelve authoring and delivery systems by their web address, network
shares, local folders, and published documentation sites. If you hand it your public docs site by
mistake, it says so and asks the question that usually settles it: **what do you open in the
morning to change a page?**

---

## What if I cannot install anything?

You can still take part. Write in your editor, commit, push. The automatic checks run on the
server for every proposed change, so your work gets validated either way. You just will not be
able to preview the result before you push it.

If you have Docker but no Java:

```bash
DAC_USE_DOCKER=1 ./scripts/build.sh
```

## What if the audit finds nothing?

That is a recognised outcome, not an error. The report opens with four numbered explanations and
what to do about each. The most common by far is a CCMS — see Case 3.

DAC will **not** invent a score for an empty folder. If it says there is nothing to measure yet,
that is the honest answer.

---

Next: [How it works](03-how-it-works.md), or jump to
[Troubleshooting](04-troubleshooting.md) if something already went wrong.
