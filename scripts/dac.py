#!/usr/bin/env python3
"""DAC pipeline runner - detect, probe, score, blockers, report in one command.

    dac.py audit  --root <dir>     read-only: detect, probe, score, blockers, audit report
    dac.py doctor --root <dir>     re-probe and diff against the last known good state
    dac.py state  --root <dir>     print a compact summary of current state

The agent orchestrates the *setup* stages, because those need judgement, adoption decisions
and prose. This runner exists so the read-only half of the pipeline is one reproducible
command rather than five, and so `doctor` has somewhere to live.

Python 3.8+, standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DAC_VERSION = "0.1.0"


def step(name):
    print("\n\033[1m==> %s\033[0m" % name if sys.stderr.isatty() else "\n==> %s" % name,
          file=sys.stderr)


def run_script(script, args):
    cmd = [sys.executable, os.path.join(HERE, script)] + args
    proc = subprocess.run(cmd)
    if proc.returncode != 0:
        print("error: %s failed with exit code %d" % (script, proc.returncode), file=sys.stderr)
        sys.exit(proc.returncode)


def state_dir(root):
    return os.path.join(root, ".dac", "state")


def load(root, name):
    p = os.path.join(state_dir(root), name)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def cmd_audit(args):
    root = os.path.abspath(args.root)
    sd = state_dir(root)
    os.makedirs(sd, exist_ok=True)

    step("Detecting your ecosystem (no credentials needed)")
    run_script("detect.py", ["--root", root, "--out", os.path.join(sd, "detect.json")])

    step("Probing what this machine and network can actually do")
    probe_args = ["--root", root, "--out", os.path.join(sd, "probe.json")]
    if args.skip_egress:
        probe_args.append("--skip-egress")
    if args.vendors:
        probe_args += ["--vendors", args.vendors]
    run_script("probe.py", probe_args)

    step("Scoring ten capability axes")
    run_script("score.py", ["--root", root, "--out", os.path.join(sd, "score.json")])

    step("Writing blocker cards and draft request messages")
    run_script("blockers.py", ["--root", root])

    step("Writing the audit report")
    run_script("report.py", ["--root", root, "--kind", "audit",
                             "--out", os.path.join(root, "dac-audit.md")])

    sco = load(root, "score.json") or {}
    blk = load(root, "blockers.json") or {}
    print("", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    print("Audit complete. Nothing on your machine or in your files was changed.",
          file=sys.stderr)
    print("", file=sys.stderr)
    det = load(root, "detect.json") or {}
    if det.get("onboarding_required"):
        print("  NO CONTENT FOUND in this folder, so there is nothing to score yet.",
              file=sys.stderr)
        print("  This is normal if your content lives in a CCMS, on a network share, or in",
              file=sys.stderr)
        print("  another folder or repository. dac-audit.md explains what to do for each case.",
              file=sys.stderr)
    else:
        print("  Score            %s/%s (%.0f%% of what your tools allow)"
              % (sco.get("total"), sco.get("total_ceiling"),
                 sco.get("percent_of_ceiling", 0)), file=sys.stderr)
        print("  Archetype        %s" % ("/".join(sco.get("archetypes", [])) or "unknown"),
              file=sys.stderr)
        print("  Worth fixing     %s" % (sco.get("binding_constraint")
                                         or "nothing - already at the ceiling"),
              file=sys.stderr)
    print("  Blocked          %d (%d degraded to a working fallback)"
          % (len(blk.get("blocked", [])), len(blk.get("degraded", []))), file=sys.stderr)
    print("", file=sys.stderr)
    print("  Read:  %s" % os.path.join(root, "dac-audit.md"), file=sys.stderr)
    print("  Cards: %s" % os.path.join(root, ".dac", "blockers"), file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    return 0


def cmd_doctor(args):
    """Re-probe and diff against the last known good state.

    This is the cheapest way to catch the failure everyone hits and nobody diagnoses: a
    version or network change that makes CI and the laptop disagree.
    """
    root = os.path.abspath(args.root)
    sd = state_dir(root)
    before = load(root, "probe.json")
    if before is None:
        print("no previous probe found - run 'audit' first", file=sys.stderr)
        return 2

    os.makedirs(sd, exist_ok=True)
    tmp = os.path.join(sd, "probe.new.json")
    step("Re-probing")
    probe_args = ["--root", root, "--out", tmp, "--quiet"]
    if args.skip_egress:
        probe_args.append("--skip-egress")
    run_script("probe.py", probe_args)
    with open(tmp, encoding="utf-8") as fh:
        after = json.load(fh)

    changes = []

    b_rt = {r["name"]: r for r in before.get("runtime", [])}
    a_rt = {r["name"]: r for r in after.get("runtime", [])}
    for name in sorted(set(b_rt) | set(a_rt)):
        b, a = b_rt.get(name, {}), a_rt.get(name, {})
        if b.get("present") != a.get("present"):
            changes.append("%s: %s -> %s" % (name,
                                             "present" if b.get("present") else "missing",
                                             "present" if a.get("present") else "missing"))
        elif b.get("version") != a.get("version"):
            changes.append("%s: version %s -> %s" % (name, b.get("version"), a.get("version")))

    b_eg = {e["id"]: e for e in before.get("egress", [])}
    a_eg = {e["id"]: e for e in after.get("egress", [])}
    for name in sorted(set(b_eg) | set(a_eg)):
        if b_eg.get(name, {}).get("verdict") != a_eg.get(name, {}).get("verdict"):
            changes.append("network %s: %s -> %s" % (name,
                                                     b_eg.get(name, {}).get("verdict"),
                                                     a_eg.get(name, {}).get("verdict")))

    b_cap, a_cap = before.get("capabilities", {}), after.get("capabilities", {})
    for k in sorted(set(b_cap) | set(a_cap)):
        if b_cap.get(k) != a_cap.get(k):
            changes.append("capability %s: %s -> %s" % (k, b_cap.get(k), a_cap.get(k)))

    print("", file=sys.stderr)
    if changes:
        print("Changes since the last probe:", file=sys.stderr)
        for c in changes:
            print("  ! %s" % c, file=sys.stderr)
        print("", file=sys.stderr)
        print("If a build started failing, one of these is very likely why.", file=sys.stderr)
    else:
        print("No change since the last probe.", file=sys.stderr)

    # Version alignment is the single most common undiagnosed cause of "works locally,
    # fails in CI" - so check it explicitly rather than leaving it to the diff.
    det = load(root, "detect.json") or {}
    local = next((r.get("version") for r in after.get("runtime", [])
                  if r["name"] == "dita-ot"), None)
    bundled = []
    for f in det.get("findings", []):
        for e in f.get("evidence", []):
            if e.get("kind") == "bundled":
                bundled.append((f["display_name"], e["detail"]))
    if bundled:
        print("", file=sys.stderr)
        print("DITA-OT versions in play:", file=sys.stderr)
        print("  local            %s" % (local or "not installed"), file=sys.stderr)
        for name, detail in bundled:
            print("  %-16s %s" % (name[:16], detail), file=sys.stderr)
        print("", file=sys.stderr)
        print("  These should match. If they do not, local and published output can differ.",
              file=sys.stderr)

    os.replace(tmp, os.path.join(sd, "probe.json"))
    return 0


def cmd_connect(args):
    """Point DAC at wherever the content actually lives.

    This is the front door for the most common first-run case: a writer whose content is
    in a CCMS, on a share, or in a repository they have never cloned. They paste one link
    and get either the content or a precise set of next steps.
    """
    argv = ["--source", args.source]
    if args.dest:
        argv += ["--dest", args.dest]
    if args.clone:
        argv.append("--clone")
    if args.full_history:
        argv.append("--full-history")
    if args.kind:
        argv += ["--kind", args.kind]
    state = os.path.join(os.path.abspath(args.root), ".dac", "state")
    os.makedirs(state, exist_ok=True)
    argv += ["--out", os.path.join(state, "connect.json")]
    # Deliberately not run_script(): a failed clone is an expected outcome that already
    # printed a clear explanation and a fix. Appending a generic "connect.py failed with
    # exit code 1" on top of that just undercuts the message the writer needs to read.
    proc = subprocess.run([sys.executable, os.path.join(HERE, "connect.py")] + argv)
    return proc.returncode


def read_journal(root):
    path = os.path.join(root, ".dac", "journal.jsonl")
    entries = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        pass
    return entries


def git(root, *args):
    try:
        proc = subprocess.run(["git"] + list(args), cwd=root, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=60)
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def cmd_blockers(args):
    """List what is still waiting on another person."""
    root = os.path.abspath(args.root)
    data = load(root, "blockers.json")
    if data is None:
        print("No blocker information yet. Run the audit first:  dac audit", file=sys.stderr)
        return 2

    blocked = data.get("blocked", [])
    degraded = data.get("degraded", [])

    if not blocked and not degraded:
        print("Nothing is blocked. Everything that could be automated was.")
        return 0

    if blocked:
        print("WAITING ON SOMEONE (%d)" % len(blocked))
        print("")
        for b in blocked:
            print("  %s  [%s, %s lane]" % (b["id"], b["severity"], b.get("lane", "?")))
            print("    %s" % b.get("what", ""))
            print("    Who:  %s" % b.get("who", "unknown"))
            print("    Cost: %s" % b.get("cost", "none"))
            if b.get("draft_message_path"):
                print("    A message you can paste and send: %s" % b["draft_message_path"])
            print("")

    if degraded:
        print("WORKING, BUT WITH A LESSER ALTERNATIVE (%d)" % len(degraded))
        print("")
        for b in degraded:
            print("  %s -> %s" % (b["id"], b.get("degraded_alternative", "")))
        print("")
        print("  These are not blocking you. Each card in .dac/blockers/ says what an")
        print("  upgrade would buy, so you can decide whether it is worth asking for.")
    return 0


def cmd_rollback(args):
    """Undo a setup run.

    Two paths, and the first is almost always the right one:

      1. If the work is on a dac/* branch, deleting that branch removes everything. This is
         why branch discipline is a rail rather than a convention.
      2. If setup ran on an existing branch, remove the files recorded in the journal - but
         never anything DAC did not create, and never anything since edited by hand.
    """
    root = os.path.abspath(args.root)
    entries = read_journal(root)
    if not entries:
        print("No journal found, so there is no recorded run to undo.", file=sys.stderr)
        print("If you ran setup, look for a dac/setup branch:  git branch --list 'dac/*'",
              file=sys.stderr)
        return 2

    rc, branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    on_dac_branch = rc == 0 and branch.startswith("dac/")

    created = []
    for e in entries:
        if args.step and e.get("id") != args.step:
            continue
        for f in e.get("files", []):
            if f not in created:
                created.append(f)

    if args.step and not created:
        print("No step with id %r found in the journal." % args.step, file=sys.stderr)
        print("Recorded steps: %s" % ", ".join(e.get("id", "?") for e in entries),
              file=sys.stderr)
        return 2

    print("Recorded run: %d step(s), %d file(s) created." % (len(entries), len(created)))
    print("")

    # Path 1: the branch is the rollback.
    if on_dac_branch and not args.step:
        rc, default = git(root, "rev-parse", "--abbrev-ref", "origin/HEAD")
        base = default.split("/")[-1] if rc == 0 and default else "main"
        print("Everything from this run is on the '%s' branch." % branch)
        print("Deleting that branch removes all of it, including this journal.")
        print("")
        print("  git checkout %s" % base)
        print("  git branch -D %s" % branch)
        print("")
        if not args.yes:
            print("Re-run with --yes to have DAC do that for you.")
            return 0
        rc, out = git(root, "checkout", base)
        if rc != 0:
            print("Could not switch to '%s':\n%s" % (base, out), file=sys.stderr)
            print("Commit or stash your current changes first.", file=sys.stderr)
            return 1
        rc, out = git(root, "branch", "-D", branch)
        if rc != 0:
            print("Could not delete '%s':\n%s" % (branch, out), file=sys.stderr)
            return 1
        print("Deleted '%s'. Nothing from the run remains." % branch)
        return 0

    # Path 2: file-level removal, with two refusals.
    print("This run is not on a dac/* branch, so files are removed individually.")
    print("")
    removable, skipped = [], []
    for rel in created:
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            skipped.append((rel, "already gone"))
            continue
        # Never discard a writer's own edits. A file DAC created but a human has since
        # changed is theirs now, not ours to delete.
        rc, out = git(root, "status", "--porcelain", "--", rel)
        if rc == 0 and out and not out.startswith(("??", "A ")):
            skipped.append((rel, "you have edited this since - leaving it alone"))
            continue
        removable.append(rel)

    for rel in removable:
        print("  remove  %s" % rel)
    for rel, why in skipped:
        print("  keep    %s  (%s)" % (rel, why))
    print("")

    if not args.yes:
        print("Nothing has been changed. Re-run with --yes to remove the files listed above.")
        return 0

    removed = 0
    for rel in removable:
        try:
            os.remove(os.path.join(root, rel))
            removed += 1
        except OSError as exc:
            print("  could not remove %s: %s" % (rel, exc), file=sys.stderr)
    print("Removed %d file(s)." % removed)
    if args.step:
        print("")
        print("Note: the journal still lists this step. Re-running setup is safe - every "
              "recipe is idempotent.")
    return 0


def cmd_interfaces(args):
    """Install the docs CLI, MCP server and optional HTTP API into the repository."""
    argv = ["--root", os.path.abspath(args.root)]
    if args.all or args.api:
        argv.append("--all")
    if args.no_cli:
        argv.append("--no-cli")
    if args.no_mcp:
        argv.append("--no-mcp")
    if args.dry_run:
        argv.append("--dry-run")
    for ide in (args.ide or []):
        argv += ["--ide", ide]
    proc = subprocess.run([sys.executable, os.path.join(HERE, "interfaces.py")] + argv)
    return proc.returncode


def cmd_state(args):
    root = os.path.abspath(args.root)
    det, prb, sco = load(root, "detect.json"), load(root, "probe.json"), load(root, "score.json")
    if not det:
        print("no state found - run 'audit' first", file=sys.stderr)
        return 2
    print("DAC state for %s" % root)
    print("  detected at    %s" % det.get("generated_at"))
    print("  archetypes     %s" % "/".join(det.get("archetypes", [])))
    print("  systems        %s" % ", ".join(f["display_name"] for f in det.get("findings", [])
                                            if f["confidence"] in ("high", "medium")))
    d = det.get("dita", {})
    print("  content        %d maps, %d topics, %d ditavals"
          % (d.get("maps", 0), d.get("topics", 0), d.get("ditavals", 0)))
    if sco:
        print("  score          %s/%s" % (sco.get("total"), sco.get("total_ceiling")))
        print("  next up        %s" % (sco.get("binding_constraint") or "-"))
    if prb:
        caps = prb.get("capabilities", {})
        print("  build path     %s" % ("native" if caps.get("can_build_native")
                                       else "container" if caps.get("can_build_container")
                                       else "NONE"))
    for w in det.get("warnings", []):
        if w["severity"] in ("high", "critical"):
            print("  ! %s" % w["id"])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="dac", description="DITA-as-Code Kit pipeline runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name, fn, helptext in (
            ("audit", cmd_audit, "detect, probe, score, blockers and the audit report"),
            ("doctor", cmd_doctor, "re-probe and diff against the last known good state"),
            ("state", cmd_state, "print a compact summary of current state")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--root", default=".")
        p.add_argument("--skip-egress", action="store_true",
                       help="make no outbound network requests")
        p.add_argument("--vendors", default="",
                       help="comma-separated vendor probes (fluid-topics,oxygen)")
        p.set_defaults(func=fn)

    pb = sub.add_parser("blockers", help="list what is still waiting on another person")
    pb.add_argument("--root", default=".")
    pb.set_defaults(func=cmd_blockers)

    pr = sub.add_parser("rollback", help="undo a setup run, or one step of it")
    pr.add_argument("--root", default=".")
    pr.add_argument("--step", help="undo only the step with this id")
    pr.add_argument("--yes", action="store_true",
                    help="actually do it; without this, only shows what would change")
    pr.set_defaults(func=cmd_rollback)

    pi = sub.add_parser("interfaces",
                        help="install the docs CLI, MCP server and HTTP API")
    pi.add_argument("--root", default=".")
    pi.add_argument("--all", action="store_true", help="include the optional HTTP API")
    pi.add_argument("--api", action="store_true", help="include the HTTP API")
    pi.add_argument("--no-cli", action="store_true")
    pi.add_argument("--no-mcp", action="store_true")
    pi.add_argument("--ide", action="append",
                    choices=["cursor", "claude", "vscode"], default=None)
    pi.add_argument("--dry-run", action="store_true",
                    help="show what would change, without changing it")
    pi.set_defaults(func=cmd_interfaces)

    pc = sub.add_parser("connect",
                        help="point DAC at a repo URL, a CCMS address, or a folder")
    pc.add_argument("--source", required=True,
                    help="a Git URL, the address you log into to write, or a folder path")
    pc.add_argument("--root", default=".")
    pc.add_argument("--dest", help="where to clone to (Git sources only)")
    pc.add_argument("--clone", action="store_true",
                    help="actually clone, rather than only printing the command")
    pc.add_argument("--full-history", action="store_true",
                    help="clone the full history instead of only the latest version")
    pc.add_argument("--kind", choices=("git", "vendor", "local_dir"),
                    help="force the classification when detection guesses wrong")
    pc.set_defaults(func=cmd_connect)

    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        print("error: not a directory: %s" % args.root, file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
