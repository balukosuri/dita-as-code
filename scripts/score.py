#!/usr/bin/env python3
"""DAC scorer - ten capability axes, 0 to 4, plus the reachable ceiling per axis.

The score is not the deliverable. It is how the executor ranks work: a team at 0 on
version control gets `git init` before it gets Schematron. The gap between the current
score and the archetype ceiling is the work list, ordered by weighted impact.

Reads detect.json and probe.json. Writes score.json.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

DAC_VERSION = "0.1.0"

# 0 = absent, 1 = manual, 2 = scripted locally, 3 = automated, 4 = automated and enforced
LEVELS = {
    0: "absent",
    1: "manual",
    2: "scripted locally",
    3: "automated",
    4: "automated and enforced",
}

AXES = [
    ("source_extractability", "Source extractability", 10,
     "Can the content be got out of its current home as portable DITA, without a human "
     "clicking through a UI?"),
    ("version_control", "Version control", 9,
     "Is the source in a VCS the rest of the company already uses?"),
    ("local_build", "Local build", 7,
     "Can a writer build the output on their own machine before pushing?"),
    ("automated_build", "Automated build", 8,
     "Does a push or pull request build the docs without anyone asking?"),
    ("structural_validation", "Structural validation", 8,
     "Are grammar, links, conrefs and keyrefs checked automatically?"),
    ("editorial_quality_gates", "Editorial quality gates", 5,
     "Are style, terminology and house rules enforced rather than remembered?"),
    ("review_workflow", "Review workflow", 6,
     "Do changes get reviewed as diffs, by the people who need to see them?"),
    ("publish_deliver", "Publish and deliver", 7,
     "Does merging publish, or does someone still do it by hand?"),
    ("reuse_dependencies", "Reuse and dependencies", 4,
     "Is shared content managed deliberately, and do shared assets resolve at edit time?"),
    ("onboarding", "Onboarding", 6,
     "Can a new writer get productive without a week of setup help?"),
]

AXIS_WEIGHT = {k: w for k, _, w, _ in AXES}

# Ceilings are honest limits, not aspirations. Archetype C genuinely cannot reach 4 on
# review or reuse, and saying otherwise is the fastest way to lose a writer's trust.
CEILINGS = {
    "A": {k: 4 for k, _, _, _ in AXES},
    "B": {"source_extractability": 3, "version_control": 4, "local_build": 3,
          "automated_build": 4, "structural_validation": 4, "editorial_quality_gates": 4,
          "review_workflow": 2, "publish_deliver": 4, "reuse_dependencies": 3,
          "onboarding": 3},
    "C": {"source_extractability": 1, "version_control": 4, "local_build": 3,
          "automated_build": 3, "structural_validation": 2, "editorial_quality_gates": 3,
          "review_workflow": 1, "publish_deliver": 3, "reuse_dependencies": 1,
          "onboarding": 3},
    "D": {"source_extractability": 2, "version_control": 3, "local_build": 2,
          "automated_build": 4, "structural_validation": 3, "editorial_quality_gates": 3,
          "review_workflow": 2, "publish_deliver": 4, "reuse_dependencies": 2,
          "onboarding": 3},
    "E": {"source_extractability": 3, "version_control": 4, "local_build": 2,
          "automated_build": 4, "structural_validation": 3, "editorial_quality_gates": 3,
          "review_workflow": 3, "publish_deliver": 4, "reuse_dependencies": 3,
          "onboarding": 3},
}

CEILING_NOTES = {
    "B": {
        "review_workflow": "Capped at 2: subject-matter experts review inside the CCMS UI, not in "
                           "pull requests. The Git mirror gives you visibility into what changed, "
                           "not a gate on it.",
        "source_extractability": "Capped at 3: no CCMS surveyed syncs DITA source to Git. Export "
                                 "is a bridge you build and schedule, so it is always a copy with "
                                 "a lag, never the live source.",
    },
    "C": {
        "source_extractability": "Capped at 1: the source is not DITA. Flare is XHTML, Author-it "
                                 "is a proprietary database, and unstructured FrameMaker is "
                                 "binary. Conversion is a project, not a pipeline step.",
        "review_workflow": "Capped at 1: without semantic XML you cannot get meaningful "
                           "component-level diffs, so review stays file-level at best.",
        "reuse_dependencies": "Capped at 1: no conref or keyref equivalent. Snippets and "
                              "variables are tool-local and do not survive extraction.",
        "structural_validation": "Capped at 2: there is no schema to validate against, so you can "
                                 "check links and build success but not structure.",
    },
}


def load_state(path, what):
    """Read a DAC state file, failing with an instruction rather than a traceback."""
    if not os.path.isfile(path):
        raise SystemExit(
            "error: %s not found.\n"
            "       Run the audit first:  dac audit\n"
            "       (expected at %s)" % (what, path))
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except ValueError:
        raise SystemExit(
            "error: %s is corrupt and cannot be read.\n"
            "       This usually means a previous run was interrupted.\n"
            "       Delete the .dac/state directory and run the audit again:\n"
            "         rm -rf .dac/state && dac audit\n"
            "       (file: %s)" % (what, path))
    except OSError as exc:
        raise SystemExit("error: cannot read %s: %s" % (path, exc))


def get(d, *path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


class Axis:
    def __init__(self, key, label, weight, question):
        self.key, self.label, self.weight, self.question = key, label, weight, question
        self.score = 0
        self.evidence = []
        self.gap_actions = []

    def at(self, score, why):
        if score >= self.score:
            self.score = score
        self.evidence.append({"score": score, "why": why})
        return self

    def needs(self, action):
        self.gap_actions.append(action)
        return self


# --------------------------------------------------------------------------------------
# per-axis rubrics
# --------------------------------------------------------------------------------------


def score_source_extractability(ax, det, prb):
    vendors = {f["vendor"]: f for f in det.get("findings", [])}
    dita = det.get("dita", {})
    if dita.get("maps") or dita.get("topics"):
        ax.at(4, "%d map(s) and %d topic(s) are already portable DITA on disk - nothing stands "
                 "between you and a pipeline." % (dita.get("maps", 0), dita.get("topics", 0)))
    if "paligo" in vendors:
        ax.at(1, "Paligo content is DocBook 5.1, not DITA. The API returns source XML, but "
                 "converting DocBook to DITA is real XSLT work.")
        ax.needs("Scope a DocBook-to-DITA conversion separately. Do not attempt it in a setup run.")
    if "madcap-flare" in vendors:
        ax.at(1, "Flare source is XHTML .htm topics, not DITA.")
        ax.needs("Treat Flare as archetype C: pipeline the project as-is, do not pretend it is "
                 "DITA.")
    if "author-it" in vendors:
        ax.at(1, "Author-it stores content in a proprietary relational database; export is a UI "
                 "operation and the automation surface is outbound only.")
    for ccms, label in (("heretto", "Heretto"), ("ixia-ccms", "MadCap IXIA CCMS"),
                        ("tridion-docs", "RWS Tridion Docs"), ("aem-guides", "AEM Guides")):
        if ccms in vendors:
            ax.at(1, "%s holds the source. No CCMS surveyed syncs DITA source to Git, so an "
                     "export bridge has to be built and scheduled." % label)
            ax.needs("Build a scheduled one-way export from %s into a Git mirror." % label)
    if not det.get("findings"):
        ax.at(0, "No structured-content system detected.")
    return ax


def score_version_control(ax, det, prb):
    inc = det.get("incumbent", {})
    if inc.get("vcs") == "git":
        ax.at(3, "The repository is already under Git.")
        if get(prb, "capabilities", "has_vcs_client"):
            ax.at(4, "Git is present locally and the repo is initialised.")
    elif inc.get("vcs"):
        ax.at(2, "Under %s rather than Git. Usable, but it isolates the docs from the "
                 "company's code review tooling." % inc["vcs"])
        ax.needs("Consider migrating to Git so docs sit alongside the code the team already "
                 "reviews.")
    else:
        ax.at(0, "No version control at all. Every other capability depends on this.")
        ax.needs("git init, add a DITA-aware .gitattributes, and make the first commit.")
    return ax


def score_local_build(ax, det, prb):
    caps = prb.get("capabilities", {})
    inc = det.get("incumbent", {})
    if caps.get("can_build_native"):
        ax.at(3, "Java and DITA-OT are both present, so local builds work today.")
    elif caps.get("can_build_container"):
        ax.at(2, "No local DITA-OT, but Docker and ghcr.io are available, so builds can run in a "
                 "container.")
    elif caps.get("can_download_dita_ot"):
        ax.at(1, "DITA-OT is downloadable but not runnable - the missing piece is a Java 17 "
                 "runtime, not network access.")
        ax.needs("Install Temurin 17, then DITA-OT. Avoid a bare 'brew install dita-ot', which "
                 "pulls a JDK far newer than the toolkit is tested against.")
    else:
        ax.at(0, "No local build path at all.")
        ax.needs("Establish either a Java 17 plus DITA-OT install or a working container runtime.")
    if any(b.get("kind", "").startswith("gradle") for b in inc.get("build_wrappers", [])):
        ax.at(min(4, ax.score + 1), "A build wrapper already exists, so the build is repeatable "
                                    "rather than a remembered command line.")
    if inc.get("project_files"):
        ax.at(4, "dita-ot-project.xml declares deliverables as data, so builds are reproducible "
                 "and machine-readable.")
    else:
        ax.needs("Add a dita-ot-project.xml so deliverables are declarative data rather than "
                 "build logic buried in a script.")
    return ax


def score_automated_build(ax, det, prb):
    inc = det.get("incumbent", {})
    ci = inc.get("ci", [])
    if not ci:
        ax.at(0, "No CI configuration found - nothing builds unless someone does it by hand.")
        ax.needs("Add a CI workflow that validates on pull request and builds on merge.")
        return ax
    ax.at(2, "CI exists (%s)." % ", ".join(c["path"] for c in ci[:3]))
    if any(c.get("mentions_dita") or c.get("uses_dita_ot_action") for c in ci):
        ax.at(3, "CI already runs DITA builds.")
        ax.at(4, "A DITA build is wired into CI and runs automatically.")
        ax.needs("Extend the existing workflow rather than adding a second one, or the repo will "
                 "produce duplicate builds.")
    else:
        ax.needs("CI exists but does not build DITA. Add a docs job to the existing pipeline.")
    return ax


def score_structural_validation(ax, det, prb):
    caps = prb.get("capabilities", {})
    inc = det.get("incumbent", {})
    dita = det.get("dita", {})
    gates = {g.get("kind") for g in inc.get("quality_gates", [])}

    # Local and CI capability are independent facts. A repo whose CI validates on every
    # pull request is validated regardless of what happens to be installed on the laptop
    # running this audit, and scoring it otherwise punishes the repo for the machine.
    if caps.get("can_validate_dtd"):
        ax.at(1, "xmllint is available locally for well-formedness and DTD validation.")
    if caps.get("can_build_native") or caps.get("can_build_container"):
        ax.at(2, "'dita validate' can run locally, resolving hrefs, keyrefs and conrefs rather "
                 "than just checking syntax.")
    else:
        ax.needs("No local validation is possible until there is a Java 17 plus DITA-OT install "
                 "or a working container runtime, so writers cannot check their work before "
                 "pushing.")

    ci_builds_dita = any(c.get("mentions_dita") or c.get("uses_dita_ot_action")
                         for c in inc.get("ci", []))
    if ci_builds_dita:
        ax.at(3, "CI runs a DITA build, so grammar and reference errors surface automatically "
                 "even when a writer cannot validate locally.")

    if "schematron" in gates:
        ax.at(max(ax.score, 3), "Schematron rules already exist in the repo.")
        if ci_builds_dita:
            ax.at(4, "Schematron plus CI means house rules are enforced, not remembered.")
    else:
        ax.needs("Add Schematron for house rules. It is the only practical way to enforce "
                 "structural style, and it belongs in CI because editor support is almost "
                 "nonexistent - the lemminx Schematron bridge has a few hundred installs.")

    if not inc.get("catalogs"):
        ax.needs("Wire XML_CATALOG_FILES to the DITA-OT catalog. Without it, validation either "
                 "fails or silently fetches DTDs over HTTP.")
    if ax.score >= 2 and not ci_builds_dita:
        ax.needs("Move validation into CI as a required check so a broken build cannot merge.")

    if dita.get("uuid_named"):
        ax.needs("UUID-based references are in use, so a filename-based link checker will pass "
                 "clean on genuinely broken links. A UUID-aware checker is required.")
    if ax.score >= 2:
        ax.needs("Add an explicit link check. A green 'dita' exit code is not sufficient evidence "
                 "of reference integrity - unresolved conrefs in the PDF stage were silent until "
                 "a 2023 fix.")
    return ax


def score_editorial_gates(ax, det, prb):
    inc = det.get("incumbent", {})
    caps = prb.get("capabilities", {})
    gates = {g.get("kind") for g in inc.get("quality_gates", [])}
    vale = next((r for r in prb.get("runtime", []) if r["name"] == "vale"), {})

    if "vale" in gates:
        ax.at(2, "A Vale configuration already exists in the repo.")
    if vale.get("present"):
        ax.at(max(ax.score, 1), "Vale %s is installed." % (vale.get("version") or "?"))
    if caps.get("can_lint_prose_dita"):
        ax.at(3, "Vale can lint .dita files, because DITA-OT is on PATH.")
    elif vale.get("present"):
        ax.needs("Vale cannot lint .dita without DITA-OT on PATH - it drives the dita command "
                 "internally. Either install Java 17 plus DITA-OT, or run prose linting only in "
                 "CI.")
    if not vale.get("present"):
        ax.needs("Install Vale and add a style configuration scoped to [*.dita].")
    if vale.get("status") == "below-floor":
        ax.needs("Upgrade Vale to 3.22.0 or later, otherwise ignore patterns do not work for DITA "
                 "and you cannot suppress false positives.")
    if any(c.get("mentions_dita") for c in inc.get("ci", [])) and ax.score >= 2:
        ax.at(4, "Editorial checks can run in CI where they are enforced.")
    ax.needs("Remember that .ditamap is not a Vale-supported extension, so map-level prose stays "
             "unlinted. Do not claim coverage you do not have.")
    return ax


def score_review_workflow(ax, det, prb):
    inc = det.get("incumbent", {})
    vendors = {f["vendor"] for f in det.get("findings", [])}
    formatters = inc.get("formatters", [])
    has_xml_prettier = any(f.get("prettier_plugin_xml") for f in formatters)

    if inc.get("vcs") == "git":
        ax.at(2, "Git is in place, so pull-request review is possible.")
    else:
        ax.at(0, "Without version control there is no diff-based review.")
    if has_xml_prettier:
        ax.at(4, "@prettier/plugin-xml normalises the XML, which is what makes DITA diffs "
                 "reviewable in a pull request.")
    elif inc.get("vcs") == "git":
        ax.at(max(ax.score, 2), "Review is possible but diffs will be noisy.")
        ax.needs("Add @prettier/plugin-xml with a pre-commit hook. Deterministic XML formatting is "
                 "the single highest-value fix for 'DITA diffs are unreadable', which is the most "
                 "common objection to DITA in a docs-as-code workflow.")
    if inc.get("hooks"):
        ax.at(min(4, ax.score + 1), "Pre-commit hooks already exist (%s)."
              % ", ".join(h["path"] for h in inc["hooks"]))
    if vendors & {"heretto", "ixia-ccms", "tridion-docs", "aem-guides"}:
        ax.needs("Subject-matter review stays in the CCMS. Treat the Git diff as a visibility "
                 "surface showing what changed, not as an approval gate.")
    return ax


def score_publish_deliver(ax, det, prb):
    inc = det.get("incumbent", {})
    vendors = {f["vendor"] for f in det.get("findings", [])}
    ci = inc.get("ci", [])
    if not ci:
        ax.at(0, "Publishing is manual.")
        ax.needs("Add a publish job so merging releases the docs.")
    else:
        ax.at(2, "CI exists and can carry a publish step.")
        if any(c.get("mentions_dita") for c in ci):
            ax.at(3, "CI already produces DITA output.")
    if "fluid-topics" in vendors:
        ax.at(max(ax.score, 3), "Fluid Topics is in play, and its ingest API is the easiest link "
                                "in the chain.")
        ax.needs("Wire the publish step to the Fluid Topics upload endpoint. Ask for "
                 "CONTENT_PUBLISHER, not KHUB_ADMIN - publishing does not need admin.")
    if "zoomin" in vendors:
        ax.needs("Zoomin is sunsetting: Salesforce ended renewals on 1 September 2025 for the "
                 "portal, In-Product Help, the API and Headless. Plan an exit rather than an "
                 "integration.")
    if "aem-guides" in vendors:
        ax.needs("AEM Guides defaults to a CSS-based Native PDF engine, not DITA-OT, so a local "
                 "DITA-OT PDF will never match the reference output. Decide which one is "
                 "authoritative before automating.")
    return ax


def score_reuse(ax, det, prb):
    dita = det.get("dita", {})
    if dita.get("conref_files"):
        ax.at(3, "%d file(s) use conref or conkeyref - element-level reuse is genuinely in use, "
                 "and this is the capability Markdown cannot replicate."
              % dita["conref_files"])
    if dita.get("keyref_files"):
        ax.at(max(ax.score, 3), "%d file(s) use keyref, so indirect addressing is established."
              % dita["keyref_files"])
    if dita.get("subjectscheme_files"):
        ax.at(4, "%d subjectScheme map(s) - controlled values are defined, which is the mature end "
                 "of DITA reuse." % dita["subjectscheme_files"])
    if not dita.get("conref_files") and (dita.get("maps") or dita.get("topics")):
        ax.at(1, "DITA is in use but no conref or keyref found, so reuse is not yet being "
                 "exploited.")
    if dita.get("ditavals"):
        ax.needs("Make sure every deliverable declares which .ditaval applies. A build that omits "
                 "--filter emits conditional content into the wrong output and still exits zero.")
    ax.needs("Default to one repository per product family. Most reuse pain is self-inflicted by "
             "sharing too granularly across too many repos.")
    return ax


def score_onboarding(ax, det, prb):
    inc = det.get("incumbent", {})
    root = det.get("root", "")
    has_devcontainer = os.path.isdir(os.path.join(root, ".devcontainer")) if root else False
    has_readme = os.path.isfile(os.path.join(root, "README.md")) if root else False
    has_contributing = os.path.isfile(os.path.join(root, "CONTRIBUTING.md")) if root else False
    has_agents = any(os.path.isfile(os.path.join(root, n))
                     for n in ("AGENTS.md", "CLAUDE.md")) if root else False

    if has_readme:
        ax.at(1, "A README exists.")
    if has_contributing:
        ax.at(2, "CONTRIBUTING.md exists.")
    if has_devcontainer:
        ax.at(3, "A devcontainer exists, so setup is close to one click.")
    else:
        ax.needs("Add a devcontainer. 'Install Java, install the toolkit, set the path' is the "
                 "single biggest onboarding failure in DITA-as-code, and a devcontainer makes the "
                 "laptop and CI the same image.")
    if has_agents:
        ax.at(4, "AGENTS.md or CLAUDE.md is present, so the team's AI IDE understands the repo.")
    else:
        ax.needs("Add AGENTS.md and CLAUDE.md describing the DITA layout, so writers can ask their "
                 "AI IDE instead of asking a colleague.")
    if not inc.get("project_files"):
        ax.needs("Document one build command that is identical locally and in CI.")
    return ax


SCORERS = {
    "source_extractability": score_source_extractability,
    "version_control": score_version_control,
    "local_build": score_local_build,
    "automated_build": score_automated_build,
    "structural_validation": score_structural_validation,
    "editorial_quality_gates": score_editorial_gates,
    "review_workflow": score_review_workflow,
    "publish_deliver": score_publish_deliver,
    "reuse_dependencies": score_reuse,
    "onboarding": score_onboarding,
}


# --------------------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------------------


def effective_ceiling(archetypes):
    """The best ceiling any detected archetype allows, per axis.

    A team with both Flare and a DITA CCMS is not limited to Flare's ceiling - their DITA
    content can go further. Take the max, then record which archetype sets the cap.
    """
    if not archetypes:
        archetypes = ["A"]
    known = [a for a in archetypes if a in CEILINGS] or ["A"]
    out, source = {}, {}
    for key, _, _, _ in AXES:
        best, best_a = -1, None
        for a in known:
            v = CEILINGS[a].get(key, 4)
            if v > best:
                best, best_a = v, a
        out[key], source[key] = best, best_a
    return out, source, known


def run(detect_path, probe_path):
    det = load_state(detect_path, "detection results (detect.json)")
    prb = load_state(probe_path, "capability probe results (probe.json)")

    archetypes = det.get("archetypes") or []
    # With no content there is nothing to assess. Still compute, because the report layout
    # expects the structure, but flag it so nothing downstream presents it as a verdict.
    assessed = bool(det.get("content_found", True))
    ceiling, ceiling_from, known = effective_ceiling(archetypes)

    axes = []
    for key, label, weight, question in AXES:
        ax = Axis(key, label, weight, question)
        SCORERS[key](ax, det, prb)
        cap = ceiling[key]
        capped = min(ax.score, cap)
        gap = max(0, cap - capped)
        note = CEILING_NOTES.get(ceiling_from[key], {}).get(key)
        axes.append({
            "key": key,
            "label": label,
            "question": question,
            "weight": weight,
            "score": capped,
            "raw_score": ax.score,
            "level": LEVELS[capped],
            "ceiling": cap,
            "ceiling_set_by_archetype": ceiling_from[key],
            "ceiling_note": note,
            "gap": gap,
            "impact": gap * weight,
            "evidence": ax.evidence,
            "actions": ax.gap_actions,
        })

    total = sum(a["score"] for a in axes)
    total_ceiling = sum(a["ceiling"] for a in axes)
    work = sorted([a for a in axes if a["gap"] > 0], key=lambda a: -a["impact"])

    return {
        "dac_version": DAC_VERSION,
        "stage": "score",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": det.get("root"),
        # Report the archetypes actually detected, not the fallback used for the ceiling
        # maths. Presenting a fallback as a finding is how DAC came to tell someone with
        # an empty folder that their content was "already portable DITA sitting in files".
        "archetypes": archetypes,
        "ceiling_basis": known,
        "assessed": assessed,
        "total": total,
        "total_ceiling": total_ceiling,
        "max_possible": 4 * len(AXES),
        "percent_of_ceiling": round(100.0 * total / total_ceiling, 1) if total_ceiling else 0.0,
        "axes": axes,
        "work_order": [{"key": a["key"], "label": a["label"], "score": a["score"],
                        "ceiling": a["ceiling"], "impact": a["impact"],
                        "actions": a["actions"]} for a in work],
        "binding_constraint": work[0]["label"] if work else None,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="DAC ten-axis capability scorer")
    ap.add_argument("--root", default=".")
    ap.add_argument("--detect", help="path to detect.json (default: <root>/.dac/state/detect.json)")
    ap.add_argument("--probe", help="path to probe.json (default: <root>/.dac/state/probe.json)")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    state = os.path.join(args.root, ".dac", "state")
    detect_path = args.detect or os.path.join(state, "detect.json")
    probe_path = args.probe or os.path.join(state, "probe.json")
    result = run(detect_path, probe_path)
    payload = json.dumps(result, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        if not args.quiet:
            print("score: wrote %s" % args.out, file=sys.stderr)
            print("  archetypes %s   total %d/%d (%.0f%% of reachable ceiling)"
                  % ("/".join(result["archetypes"]), result["total"], result["total_ceiling"],
                     result["percent_of_ceiling"]), file=sys.stderr)
            for a in result["axes"]:
                bar = "#" * a["score"] + "." * (a["ceiling"] - a["score"])
                print("  %-26s %d/%d %-6s %s" % (a["label"], a["score"], a["ceiling"], bar,
                                                 a["level"]), file=sys.stderr)
            if result["binding_constraint"]:
                print("  binding constraint: %s" % result["binding_constraint"], file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
