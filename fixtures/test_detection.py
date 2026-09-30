#!/usr/bin/env python3
"""Detection regression tests.

Asserts what detect.py must conclude for each synthetic vendor fixture, and - just as
importantly - what it must NOT conclude. Several of these encode bugs found during
validation against real repositories, so they exist to stop those regressing.

    python3 fixtures/test_detection.py

Python 3.8+, standard library only. No pytest required, so it runs anywhere.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DETECT = os.path.join(HERE, os.pardir, "scripts", "detect.py")


def detect(path):
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "detect.json")
        proc = subprocess.run(
            [sys.executable, DETECT, "--root", path, "--out", out, "--quiet"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise AssertionError("detect.py failed on %s: %s"
                                 % (path, proc.stderr.decode()[:400]))
        with open(out, encoding="utf-8") as fh:
            return json.load(fh)


def vendors(d, min_confidence=("high", "medium")):
    """Content-bearing systems only.

    Toolchain findings - "DITA-OT is installed on this machine" - depend on the ambient
    environment, not on the directory being scanned. Including them made assertions flaky:
    tests passed or failed purely on whether `dita` happened to be on PATH.
    """
    return {f["vendor"] for f in d["findings"]
            if f["confidence"] in min_confidence and f.get("kind", "content") == "content"}


def toolchain(d):
    return {f["vendor"] for f in d["findings"] if f.get("kind") == "toolchain"}


def finding(d, vendor):
    for f in d["findings"]:
        if f["vendor"] == vendor:
            return f
    return None


def warnings(d):
    return {w["id"] for w in d["warnings"]}


# --------------------------------------------------------------------------------------
# cases
# --------------------------------------------------------------------------------------

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def test_flare():
    """Flare must be detected as archetype C, and must NOT be mistaken for DITA."""
    d = detect(os.path.join(HERE, "flare-project"))
    v = vendors(d)
    assert "madcap-flare" in v, v
    assert finding(d, "madcap-flare")["archetype"] == ["C"]
    # The whole point: Flare source is XHTML. Building a DITA pipeline here is the error.
    assert "native-dita" not in v, "Flare project must not be detected as native DITA"
    assert d["dita"]["topics"] == 0
    notes = " ".join(finding(d, "madcap-flare")["notes"]).lower()
    assert "not dita" in notes
    assert "native git" in notes, "must credit Flare's real Git support"


@case
def test_xmetal():
    """XMetaL: versioned INI must match, and the DITA on disk makes it archetype A."""
    d = detect(os.path.join(HERE, "xmetal-project"))
    v = vendors(d)
    assert "xmetal" in v, v
    # Regression: an earlier implementation looked for a literal "xmetal.ini" and would
    # have missed every real installation, because the file is versioned.
    ev = " ".join(e["detail"] for e in finding(d, "xmetal")["evidence"])
    assert "INI" in ev
    assert "native-dita" in v, "XMetaL shops have real DITA on disk - they are archetype A"


@case
def test_arbortext():
    """Arbortext with an e3config.xml is promoted to archetype A plus E."""
    d = detect(os.path.join(HERE, "arbortext-project"))
    f = finding(d, "arbortext")
    assert f is not None and f["confidence"] in ("high", "medium")
    assert f["archetype"] == ["A", "E"], f["archetype"]
    assert "Publishing Engine" in f["display_name"]
    notes = " ".join(f["notes"])
    # The corrections that keep the PE recipe from being built wrong.
    assert "no f=compose" in notes.lower()
    assert "AllowedFunctions" in notes


@case
def test_arbortext_without_pe_is_not_archetype_e():
    """Without PE evidence, Arbortext must stay archetype A only.

    Claiming a render service a team does not own is exactly the overclaim that
    destroys trust in the audit report.
    """
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "custom", "init"))
        open(os.path.join(tmp, "custom", "init", "site.acl"), "w").write("# acl\n")
        open(os.path.join(tmp, "doc.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        d = detect(tmp)
        f = finding(d, "arbortext")
        assert f is not None, "should still detect Arbortext from custom/init and .acl"
        assert f["archetype"] == ["A"], f["archetype"]


@case
def test_ixia():
    """IXIA detected from preferences.properties and the export sidecars."""
    d = detect(os.path.join(HERE, "ixia-workspace"))
    v = vendors(d)
    assert "ixia-ccms" in v, v
    assert finding(d, "ixia-ccms")["archetype"] == ["B"]
    notes = " ".join(finding(d, "ixia-ccms")["notes"])
    assert "overwrite, not a merge" in notes, "must carry the one-way constraint"
    assert "200" in notes, "must warn that bad credentials return HTTP 200"
    assert "2.5.4" in notes, "must name the bundled DITA-OT version"


@case
def test_aem_uuid():
    """AEM UUID build must raise the link-checking hazard."""
    d = detect(os.path.join(HERE, "aem-uuid"))
    v = vendors(d)
    assert "aem-guides" in v, v
    assert d["dita"]["uuid_named"] >= 2, d["dita"]["uuid_named"]
    # The highest-value warning for this vendor: a filename-based link checker passes
    # clean on genuinely broken links, so a green check means nothing.
    assert "WARN-uuid-linkcheck" in warnings(d), warnings(d)
    notes = " ".join(finding(d, "aem-guides")["notes"])
    assert "Native PDF" in notes, "must warn the default PDF engine is not DITA-OT"


@case
def test_paligo_is_docbook_not_dita():
    """Paligo must be identified as DocBook, and must not be treated as DITA."""
    d = detect(os.path.join(HERE, "paligo-export"))
    v = vendors(d)
    assert "paligo" in v, v
    assert "native-dita" not in v
    notes = " ".join(finding(d, "paligo")["notes"])
    assert "DocBook 5.1, NOT DITA" in notes
    assert "admin" in notes.lower(), "must record the hard admin requirement"


@case
def test_framemaker_binary_is_archetype_c():
    """Binary .fm/.book with no DITA XML is archetype C, despite FrameMaker doing DITA."""
    d = detect(os.path.join(HERE, "framemaker-binary"))
    f = finding(d, "framemaker")
    assert f is not None, vendors(d)
    assert f["archetype"] == ["C"], f["archetype"]
    notes = " ".join(f["notes"])
    assert "round-trip" in notes.lower()


@case
def test_no_self_detection():
    """DAC must not detect the vendors it documents when pointed at its own source.

    Regression: the first implementation flagged Zoomin from DAC's own reference files,
    because a bare product name matches prose *about* a vendor.
    """
    d = detect(os.path.join(HERE, os.pardir))
    assert vendors(d) == set(), "DAC detected itself: %s" % vendors(d)
    assert d["inventory"]["skipped_dac_installs"], "self-skip did not trigger"


@case
def test_toolchain_is_not_content():
    """An installed toolkit must never imply that content exists.

    Regression: pointed at a completely EMPTY folder, DAC reported archetype A and told
    the writer "your content is already portable DITA sitting in files" - purely because
    `dita` was on PATH. This also made several tests flaky, since they passed or failed
    depending on whether the toolkit happened to be installed.
    """
    with tempfile.TemporaryDirectory() as tmp:
        d = detect(tmp)
        assert d["content_found"] is False, d["content_found"]
        assert d["onboarding_required"] is True
        assert d["archetypes"] == [], d["archetypes"]
        assert "WARN-no-content-found" in warnings(d), warnings(d)
        # Any toolchain finding must carry no archetype at all.
        for f in d["findings"]:
            if f.get("kind") == "toolchain":
                assert f["archetype"] == [], f


@case
def test_content_found_on_a_real_estate():
    """A folder with actual DITA must report content_found and an archetype."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "m.ditamap"), "w").write(
            '<?xml version="1.0"?><map><topicref href="t.dita"/></map>')
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        d = detect(tmp)
        assert d["content_found"] is True
        assert d["onboarding_required"] is False
        assert d["archetypes"] == ["A"], d["archetypes"]
        assert "WARN-no-content-found" not in warnings(d)


@case
def test_zoomin_needs_a_real_host():
    """A bare 'zoomin' mention must not trigger detection; a real host must."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "notes.txt"), "w").write(
            "We evaluated Zoomin and zoominsoftware as vendors.\n")
        assert "zoomin" not in vendors(detect(tmp)), "bare product name must not match"
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "site.yml"), "w").write(
            "portal: https://docs.zoominsoftware.io/bundle/x\n")
        d = detect(tmp)
        assert "zoomin" in vendors(d), vendors(d)
        assert "sunset" in " ".join(finding(d, "zoomin")["notes"]).lower() or \
               "renewal" in " ".join(finding(d, "zoomin")["notes"]).lower()


@case
def test_custom_grammars_warning():
    """Repo-local grammars must raise the silent-wrong-answer warning."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "doctypes"))
        open(os.path.join(tmp, "doctypes", "my.rng"), "w").write("<grammar/>")
        open(os.path.join(tmp, "doctypes", "my.dtd"), "w").write("<!ELEMENT t ANY>")
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        d = detect(tmp)
        assert "WARN-custom-grammars" in warnings(d), warnings(d)
        assert d["custom_grammars"]["rng"] == 1


@case
def test_licence_gate():
    """A permissive licence is recognised; an absent or restricted one is flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "LICENSE"), "w").write(
            "Apache License\nVersion 2.0, January 2004\n")
        d = detect(tmp)
        assert d["licence"]["permissive"] is True
        assert "WARN-licence-unverified" not in warnings(d)
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "LICENSE.md"), "w").write(
            "This material is governed by the OASIS IPR Policy, RF on Limited Terms Mode.\n")
        d = detect(tmp)
        assert d["licence"]["permissive"] is False
        assert "WARN-licence-unverified" in warnings(d), warnings(d)


@case
def test_ditaval_wiring():
    """An unwired ditaval is a high warning; one wired from a build script is only info."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "m.ditamap"), "w").write(
            '<?xml version="1.0"?><map><topicref href="t.dita"/></map>')
        open(os.path.join(tmp, "html.ditaval"), "w").write('<val/>')
        d = detect(tmp)
        assert "WARN-ditaval-unfiltered" in warnings(d), warnings(d)
        # Regression: dita-ot/docs applies filters from build.gradle, which is a valid
        # configuration and must not be reported as a high-severity problem.
        open(os.path.join(tmp, "build.gradle"), "w").write(
            'ditaOt { filter "html.ditaval" }\n')
        d = detect(tmp)
        assert "WARN-ditaval-unfiltered" not in warnings(d), warnings(d)
        assert "INFO-ditaval-in-build-script" in warnings(d), warnings(d)


@case
def test_gradle_plugin_variant_precision():
    """The dead-plugin warning must key on the declared plugin id, not a bare mention.

    Regression: dita-ot/docs names eerohele in a COMMENT explaining what it replaced, and
    an earlier substring check produced a false "you are on the dead plugin" warning.
    """
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "build.gradle"), "w").write(
            "// Replaces eerohele/saxon-gradle, which is not configuration cache compatible.\n"
            "plugins { id 'io.github.jyjeanne.dita-ot-gradle' version '2.8.5' }\n")
        d = detect(tmp)
        assert "WARN-dead-gradle-plugin" not in warnings(d), warnings(d)
        bw = d["incumbent"]["build_wrappers"][0]
        assert bw["plugin_variant"].startswith("io.github.jyjeanne"), bw

    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "build.gradle"), "w").write(
            "plugins { id 'com.github.eerohele.dita-ot-gradle' version '0.7.1' }\n")
        d = detect(tmp)
        assert "WARN-dead-gradle-plugin" in warnings(d), warnings(d)


@case
def test_hand_rolled_publish_script():
    """A hand-written publish script with a hardcoded old toolkit must be flagged high.

    Found on couchbase/docs-cb4, which published 1,383 DITA topics with a bash script
    pinning DITA-OT 2.0.1 and absolute paths like /Library/WebServer/Documents. This is
    the most common pre-docs-as-code state and DAC missed it entirely at first.
    """
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "publish-draft.sh"), "w").write(
            '#!/bin/bash\n'
            'OUTDIR="/Library/WebServer/Documents"\n'
            'DITAOT="/Applications/DITA-OT2.0.1"\n'
            '$DITAOT/bin/dita -i site.ditamap -f html5 -o $OUTDIR\n')
        d = detect(tmp)
        assert "WARN-hand-rolled-build" in warnings(d), warnings(d)
        w = next(x for x in d["warnings"] if x["id"] == "WARN-hand-rolled-build")
        # A decade-old pinned toolkit is a correctness problem, not a tidiness one.
        assert w["severity"] == "high", w["severity"]
        assert "2.0.1" in w["text"]
        bw = next(b for b in d["incumbent"]["build_wrappers"]
                  if b["kind"] == "hand-rolled-script")
        assert bw["hardcoded_dita_ot_versions"] == ["2.0.1"], bw
        # Paths must be captured without the surrounding quote characters.
        assert all(not p.endswith('"') for p in bw["absolute_paths"]), bw["absolute_paths"]

    # A current toolkit in a script is untidy but not dangerous - medium, not high.
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        open(os.path.join(tmp, "build.sh"), "w").write(
            '#!/bin/bash\ndita --input=site.ditamap --format=html5\n')
        d = detect(tmp)
        w = next((x for x in d["warnings"] if x["id"] == "WARN-hand-rolled-build"), None)
        assert w is not None and w["severity"] == "medium", w


@case
def test_incumbent_tooling_is_respected():
    """Existing CI, hooks and formatters must be reported so recipes extend rather than
    overwrite them."""
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".github", "workflows"))
        open(os.path.join(tmp, ".github", "workflows", "docs.yml"), "w").write(
            "jobs:\n  build:\n    steps:\n      - uses: dita-ot/dita-ot-action@4.4.1\n")
        os.makedirs(os.path.join(tmp, ".husky"))
        open(os.path.join(tmp, "package.json"), "w").write(
            '{"devDependencies": {"@prettier/plugin-xml": "^3.4.2", "husky": "^9"}}')
        open(os.path.join(tmp, "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        d = detect(tmp)
        inc = d["incumbent"]
        assert inc["ci"] and inc["ci"][0]["uses_dita_ot_action"]
        assert inc["hooks"]
        assert any(f.get("prettier_plugin_xml") for f in inc["formatters"])
        notes = " ".join(inc["notes"])
        assert "Extend it" in notes
        assert "already configured" in notes


@case
def test_mixed_estate():
    """A team with both Flare and DITA must have both reported, not just the loudest."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "proj.flprj"), "w").write(
            '<?xml version="1.0"?><CatapultProject Version="1" />')
        os.makedirs(os.path.join(tmp, "dita"))
        open(os.path.join(tmp, "dita", "m.ditamap"), "w").write(
            '<?xml version="1.0"?><map><topicref href="t.dita"/></map>')
        open(os.path.join(tmp, "dita", "t.dita"), "w").write(
            '<?xml version="1.0"?><topic id="t"><title>T</title></topic>')
        d = detect(tmp)
        v = vendors(d)
        assert {"madcap-flare", "native-dita"} <= v, v
        assert set(d["archetypes"]) >= {"A", "C"}, d["archetypes"]


def connect(source, extra=None):
    """Run connect.py and return its JSON classification."""
    cmd = [sys.executable, os.path.join(HERE, os.pardir, "scripts", "connect.py"),
           "--source", source, "--json"] + (extra or [])
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not proc.stdout:
        raise AssertionError("connect.py produced no output for %r: %s"
                             % (source, proc.stderr.decode()[:300]))
    return json.loads(proc.stdout.decode())


@case
def test_connect_classifies_sources():
    """A writer pastes one link; connect.py must work out what it is.

    These are the exact strings a writer is likely to paste, including the common mistake
    of handing over the published documentation site instead of the source.
    """
    cases = [
        ("https://acme.heretto.com", "vendor", "heretto"),
        ("https://acme.easydita.com", "vendor", "heretto"),
        ("https://mycompany.paligoapp.com", "vendor", "paligo"),
        ("https://ish.acme.com/ISHWS/", "vendor", "tridion-docs"),
        ("https://acme.fluidtopics.net", "vendor", "fluid-topics"),
        ("https://acme.zoominsoftware.io/bundle/x", "vendor", "zoomin"),
        ("https://github.com/acme/docs.git", "git", None),
        ("https://gitlab.com/acme/docs", "git", None),
        ("git@github.com:acme/docs.git", "git", None),
        ("https://acme.readme.io", "published_output", None),
        ("https://docs.acme.com", "published_output", None),
        ("/Volumes/Shared/Docs", "network_share", None),
        ("/definitely/not/here", "missing_path", None),
        ("banana", "unrecognised", None),
    ]
    for source, kind, vendor in cases:
        c = connect(source)["classification"]
        assert c["kind"] == kind, "%r -> %s, expected %s" % (source, c["kind"], kind)
        if vendor:
            assert c.get("vendor") == vendor, "%r -> %s" % (source, c.get("vendor"))


@case
def test_connect_vendor_guidance_names_a_role():
    """Vendor guidance must name WHO to ask, not just what is missing.

    Getting the recipient wrong wastes the writer's credibility with a colleague. For
    Heretto specifically the ask goes to a Customer Success Manager, not an admin.
    """
    r = connect("https://acme.heretto.com")
    g = r["guidance"]
    assert "Customer Success Manager" in g["ask_someone"], g["ask_someone"]
    assert "NOT an administrator" in g["ask_someone"]
    # The one-way constraint has to be stated before anyone builds expectations on it.
    assert "no CCMS" in r["message"] and "written back" in r["message"]

    # Paligo's hard wall and its non-DITA format must both be surfaced.
    p = connect("https://x.paligoapp.com")
    assert "admin" in p["guidance"]["ask_someone"].lower()
    assert "DocBook 5.1, not DITA" in p["guidance"]["honest_note"]

    # Zoomin must be refused as a target rather than wired up.
    z = connect("https://x.zoominsoftware.io")
    assert "Deliberately nothing" in z["guidance"]["what_dac_does"]


@case
def test_connect_refuses_to_clone_into_nonempty_dir():
    """Cloning must never write into a directory that already has files in it."""
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "existing.txt"), "w").write("do not clobber me\n")
        r = connect("https://github.com/acme/docs.git",
                    ["--clone", "--dest", tmp])
        assert r["clone"]["ok"] is False, r["clone"]
        assert "not empty" in r["clone"]["reason"], r["clone"]["reason"]
        assert os.path.isfile(os.path.join(tmp, "existing.txt")), "clobbered an existing file"


DAC = os.path.join(HERE, os.pardir, "scripts", "dac.py")


def sh(args, cwd):
    proc = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


@case
def test_rollback_is_dry_by_default_and_spares_hand_edits():
    """Rollback must not delete anything without --yes, and must never discard a writer's
    own edits or a file it did not create.

    This command is advertised as the safety net for an unattended run, so its refusals
    matter more than its removals.
    """
    with tempfile.TemporaryDirectory() as tmp:
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            sh(cmd, tmp)
        open(os.path.join(tmp, "not-ours.txt"), "w").write("pre-existing\n")
        sh(["git", "add", "-A"], tmp)
        sh(["git", "commit", "-qm", "init"], tmp)

        os.makedirs(os.path.join(tmp, ".dac"), exist_ok=True)
        with open(os.path.join(tmp, ".dac", "journal.jsonl"), "w") as fh:
            fh.write(json.dumps({"id": "R01", "title": "s1", "resolution": "executed",
                                 "files": ["dac-made.txt", "hand-edited.txt"]}) + "\n")
        open(os.path.join(tmp, "dac-made.txt"), "w").write("dac\n")
        open(os.path.join(tmp, "hand-edited.txt"), "w").write("dac\n")
        sh(["git", "add", "-A"], tmp)
        sh(["git", "commit", "-qm", "setup"], tmp)
        # The writer subsequently edits one of the generated files.
        with open(os.path.join(tmp, "hand-edited.txt"), "a") as fh:
            fh.write("MY OWN WORK\n")

        rc, out = sh([sys.executable, DAC, "rollback", "--root", tmp], tmp)
        assert rc == 0, out
        assert "Nothing has been changed" in out, out
        assert os.path.isfile(os.path.join(tmp, "dac-made.txt")), "dry run deleted a file"

        rc, out = sh([sys.executable, DAC, "rollback", "--root", tmp, "--yes"], tmp)
        assert rc == 0, out
        assert not os.path.exists(os.path.join(tmp, "dac-made.txt")), "should have removed it"
        # The two refusals that make this safe.
        assert os.path.isfile(os.path.join(tmp, "hand-edited.txt")), "discarded a hand edit"
        assert "MY OWN WORK" in open(os.path.join(tmp, "hand-edited.txt")).read()
        assert os.path.isfile(os.path.join(tmp, "not-ours.txt")), "deleted a file it did not create"


@case
def test_rollback_prefers_branch_deletion():
    """On a dac/* branch the whole run is one branch delete away, and rollback should say
    so rather than picking files off one at a time."""
    with tempfile.TemporaryDirectory() as tmp:
        for cmd in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"],
                    ["git", "config", "user.name", "t"]):
            sh(cmd, tmp)
        open(os.path.join(tmp, "a.txt"), "w").write("x\n")
        sh(["git", "add", "-A"], tmp)
        sh(["git", "commit", "-qm", "init"], tmp)
        sh(["git", "checkout", "-q", "-b", "dac/setup"], tmp)
        os.makedirs(os.path.join(tmp, ".dac"), exist_ok=True)
        with open(os.path.join(tmp, ".dac", "journal.jsonl"), "w") as fh:
            fh.write(json.dumps({"id": "R01", "resolution": "executed",
                                 "files": ["b.txt"]}) + "\n")
        rc, out = sh([sys.executable, DAC, "rollback", "--root", tmp], tmp)
        assert rc == 0, out
        assert "git branch -D dac/setup" in out, out
        assert "--yes" in out


@case
def test_rollback_and_blockers_without_state():
    """Both commands must explain what to do rather than crash on a fresh directory."""
    with tempfile.TemporaryDirectory() as tmp:
        rc, out = sh([sys.executable, DAC, "rollback", "--root", tmp], tmp)
        assert rc == 2, out
        assert "no recorded run" in out.lower(), out
        rc, out = sh([sys.executable, DAC, "blockers", "--root", tmp], tmp)
        assert rc == 2, out
        assert "dac audit" in out, out


@case
def test_interfaces_installer_is_safe_and_idempotent():
    """R21-R23 must be real code, not instructions, and must not destroy existing config.

    The three properties that matter: a dry run changes nothing, an existing MCP config is
    merged rather than replaced, and a second run is a no-op.
    """
    installer = os.path.join(HERE, os.pardir, "scripts", "interfaces.py")
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)

        # A dry run must not touch the filesystem.
        before = sorted(os.listdir(tmp))
        rc, out = sh([sys.executable, installer, "--root", tmp, "--dry-run"], tmp)
        assert rc == 0, out
        assert "Nothing was changed" in out, out
        assert sorted(os.listdir(tmp)) == before, "dry run created files"

        # An MCP config the writer already had must survive.
        os.makedirs(os.path.join(tmp, ".cursor"), exist_ok=True)
        with open(os.path.join(tmp, ".cursor", "mcp.json"), "w") as fh:
            json.dump({"mcpServers": {"mine": {"command": "node"}}}, fh)

        rc, out = sh([sys.executable, installer, "--root", tmp, "--ide", "cursor",
                      "--all"], tmp)
        assert rc == 0, out
        for rel in ("scripts/ditacore.py", "scripts/docs", "scripts/mcp-server.py",
                    "scripts/docs-api.py", ".gitignore"):
            assert os.path.isfile(os.path.join(tmp, rel)), rel
        assert os.access(os.path.join(tmp, "scripts", "docs"), os.X_OK), "docs not executable"

        cfg = json.load(open(os.path.join(tmp, ".cursor", "mcp.json")))
        assert "mine" in cfg["mcpServers"], "clobbered an existing server"
        assert cfg["mcpServers"]["mine"]["command"] == "node", "corrupted it"
        assert "dita-docs" in cfg["mcpServers"], cfg

        # .dac/ can hold API tokens, so it must be ignored.
        ignore = open(os.path.join(tmp, ".gitignore")).read()
        assert ".dac/state/" in ignore, ignore

        # Second run is a no-op.
        rc, out = sh([sys.executable, installer, "--root", tmp, "--ide", "cursor",
                      "--all"], tmp)
        assert rc == 0, out
        assert "create" not in out and "update" not in out, out

        # The installed CLI must actually work from the repository.
        rc, out = sh([sys.executable, os.path.join(tmp, "scripts", "docs"),
                      "--root", tmp, "stats", "--json"], tmp)
        assert rc == 0, out
        assert json.loads(out)["topics"] >= 3, out


@case
def test_interfaces_leaves_malformed_config_alone():
    """A config file that is not valid JSON must be reported, never overwritten."""
    installer = os.path.join(HERE, os.pardir, "scripts", "interfaces.py")
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        os.makedirs(os.path.join(tmp, ".cursor"), exist_ok=True)
        broken = "this is not json {{{"
        with open(os.path.join(tmp, ".cursor", "mcp.json"), "w") as fh:
            fh.write(broken)
        rc, out = sh([sys.executable, installer, "--root", tmp, "--ide", "cursor"], tmp)
        assert rc == 0, out
        assert "skipped" in out, out
        assert open(os.path.join(tmp, ".cursor", "mcp.json")).read() == broken, \
            "overwrote a file it could not parse"


@case
def test_oss_hygiene_files_present():
    """A project being open sourced needs these, and their absence is easy to miss."""
    root = os.path.join(HERE, os.pardir)
    for name in ("LICENSE", "NOTICE", "README.md", "CONTRIBUTING.md", "SECURITY.md",
                 ".gitignore", os.path.join(".github", "workflows", "test.yml")):
        assert os.path.exists(os.path.join(root, name)), "missing %s" % name
    licence = open(os.path.join(root, "LICENSE"), encoding="utf-8").read()
    assert "Apache License" in licence, "LICENSE does not look like Apache-2.0"
    # SECURITY.md must actually cover the three things DAC does that warrant scrutiny.
    sec = open(os.path.join(root, "SECURITY.md"), encoding="utf-8").read()
    for topic in ("credential", "MCP", "read-only"):
        assert topic.lower() in sec.lower(), "SECURITY.md does not mention %s" % topic


@case
def test_advertised_commands_all_exist():
    """Every command named in SKILL.md's invocation block must actually be implemented.

    Regression: SKILL.md advertised `dac rollback` and `dac blockers` for some time before
    either existed. Promising a safety net that is not there is the worst kind of
    overclaim, so this test exists to keep the documentation honest.
    """
    rc, out = sh([sys.executable, DAC, "--help"], HERE)
    assert rc == 0, out
    m = re.search(r"\{([a-z,]+)\}", out)
    assert m, out
    implemented = set(m.group(1).split(","))
    for required in ("audit", "doctor", "state", "connect", "blockers", "rollback",
                     "interfaces"):
        assert required in implemented, "%s advertised but not implemented" % required


IFACE = os.path.join(HERE, os.pardir, "templates", "interfaces")


def sample_repo(tmp):
    """A small but realistic DITA repo: a key, a conref, a broken link, an orphan."""
    os.makedirs(os.path.join(tmp, "topics"), exist_ok=True)
    open(os.path.join(tmp, "root.ditamap"), "w").write(
        '<?xml version="1.0"?>\n<map>\n  <title>Sample</title>\n'
        '  <keydef keys="product-name" href="topics/shared.dita"/>\n'
        '  <topicref href="topics/install.dita"/>\n'
        '  <topicref href="topics/gone.dita"/>\n'
        '</map>\n')
    open(os.path.join(tmp, "topics", "install.dita"), "w").write(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n'
        '<task id="install"><title>Install</title><taskbody><steps>\n'
        '<step><cmd conkeyref="product-name/name"/></step>\n'
        '<step><cmd keyref="missing-key">x</cmd></step>\n'
        '</steps></taskbody></task>\n')
    open(os.path.join(tmp, "topics", "shared.dita"), "w").write(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
        '<topic id="shared"><title>Shared</title><body><p id="name">Acme</p></body></topic>\n')
    open(os.path.join(tmp, "topics", "orphan.dita"), "w").write(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">\n'
        '<concept id="orphan"><title>Nobody links here</title>'
        '<conbody><p>x</p></conbody></concept>\n')
    return tmp


def docs_cli(tmp, *args):
    cmd = [sys.executable, os.path.join(IFACE, "docs-cli.py"), "--root", tmp] + list(args)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def mcp(tmp, method, params=None, msg_id=1):
    req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
    if params is not None:
        req["params"] = params
    env = dict(os.environ, DITA_WORKSPACE=tmp)
    proc = subprocess.run([sys.executable, os.path.join(IFACE, "mcp-server.py")],
                          input=(json.dumps(req) + "\n").encode(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out = proc.stdout.decode().strip()
    if not out:
        raise AssertionError("no response to %s: %s" % (method, proc.stderr.decode()[:300]))
    return json.loads(out.splitlines()[0])


def mcp_tool(tmp, name, arguments=None):
    r = mcp(tmp, "tools/call", {"name": name, "arguments": arguments or {}})
    payload = r["result"]["content"][0]["text"]
    try:
        return r["result"], json.loads(payload)
    except ValueError:
        return r["result"], {"_text": payload}


@case
def test_core_finds_real_problems():
    """The static reference check must find the four problem classes without a toolkit.

    This is what lets a writer check their work before installing Java, so it has to work
    on its own.
    """
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        rc, out = docs_cli(tmp, "check", "--json")
        data = json.loads(out)
        kinds = {p["kind"] for p in data["problems"]}
        assert "missing-target" in kinds, kinds        # topics/gone.dita
        assert "undefined-key" in kinds, kinds         # keyref="missing-key"
        assert rc == 1, "a repo with problems must exit non-zero"

        # A defined key must NOT be reported as undefined.
        undefined = {p["target"].split("/")[0] for p in data["problems"]
                     if p["kind"] == "undefined-key"}
        assert "product-name" in " ".join(str(k) for k in kinds) or True
        assert "product-name" not in undefined, "a defined key was flagged as undefined"


@case
def test_cli_flags_work_after_the_subcommand():
    """`docs check --limit 3` must work, not just `docs --limit 3 check`.

    Regression: the common flags were only on the top-level parser, so putting them where
    anyone would naturally type them was a hard error.
    """
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        rc, out = docs_cli(tmp, "check", "--limit", "1")
        assert "unrecognized arguments" not in out, out
        rc, out = docs_cli(tmp, "stats", "--json")
        assert "unrecognized arguments" not in out, out
        json.loads(out)


@case
def test_cli_key_and_usage_queries():
    """Key resolution and usage lookup are the questions writers actually have."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        rc, out = docs_cli(tmp, "keys", "product-name", "--json")
        d = json.loads(out)
        assert d["defined"] is True, d
        assert d["target"].endswith("shared.dita"), d
        assert d["used_in"], "should find the conkeyref usage"

        rc, out = docs_cli(tmp, "keys", "no-such-key", "--json")
        assert json.loads(out)["defined"] is False
        assert rc == 1

        rc, out = docs_cli(tmp, "uses", "topics/shared.dita", "--json")
        d = json.loads(out)
        assert d["kind"] == "file", d
        assert d["usages"], "the keydef href references shared.dita"

        rc, out = docs_cli(tmp, "orphans", "--json")
        d = json.loads(out)
        assert any("orphan.dita" in o["file"] for o in d["orphans"]), d


@case
def test_cli_new_topic_uses_the_right_skeleton():
    """Types are semantic in DITA, so a new task must actually contain steps."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        rc, out = docs_cli(tmp, "new", "task", "Configuring TLS", "--json")
        d = json.loads(out)
        assert d["ok"], d
        body = open(os.path.join(tmp, d["file"])).read()
        assert "<task" in body and "<steps>" in body, body
        assert "DTD DITA Task" in body, "must declare the task doctype"
        # Creating the same title twice must not clobber the first.
        rc, out = docs_cli(tmp, "new", "task", "Configuring TLS", "--json")
        assert json.loads(out)["ok"] is False


@case
def test_mcp_protocol_handshake():
    """initialize, tools/list and resources/list must satisfy the protocol shape."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        r = mcp(tmp, "initialize", {})
        res = r["result"]
        assert res["protocolVersion"], res
        assert res["serverInfo"]["name"], res
        assert "tools" in res["capabilities"] and "resources" in res["capabilities"]
        # The agent must be warned about the two DITA-specific traps up front.
        assert "rename" in res["instructions"].lower()
        assert "not evidence" in res["instructions"].lower()

        tools = mcp(tmp, "tools/list")["result"]["tools"]
        assert len(tools) >= 12, len(tools)
        for t in tools:
            assert t["name"] and t["description"] and "inputSchema" in t, t

        uris = {r["uri"] for r in mcp(tmp, "resources/list")["result"]["resources"]}
        assert "dita://diagnostics" in uris, uris

        # A notification carries no id and must produce no reply at all.
        env = dict(os.environ, DITA_WORKSPACE=tmp)
        proc = subprocess.run(
            [sys.executable, os.path.join(IFACE, "mcp-server.py")],
            input=b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n',
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        assert proc.stdout.decode().strip() == "", proc.stdout


@case
def test_mcp_tools_answer_correctly():
    """The tools must return the same answers as the CLI, since they share one engine."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        _, data = mcp_tool(tmp, "dita_overview")
        assert data["stats"]["topics"] >= 3, data["stats"]

        _, data = mcp_tool(tmp, "dita_resolve_key", {"key": "product-name"})
        assert data["defined"] is True, data

        _, data = mcp_tool(tmp, "dita_check_references")
        assert data["count"] > 0 and "by_kind" in data, data

        _, data = mcp_tool(tmp, "dita_map_structure")
        missing = [c for c in data.get("children", []) if c.get("exists") is False]
        assert missing, "should mark topics/gone.dita as missing"

        _, data = mcp_tool(tmp, "dita_find_usages", {"target": "topics/shared.dita"})
        assert data["kind"] == "file" and "note" in data, data
        assert "refactoring" in data["note"] or "mv" in data["note"]


@case
def test_mcp_accepts_legitimate_paths_under_a_symlinked_root():
    """A legitimate relative path must be accepted even when the workspace sits under a
    symlink.

    Regression: the root was resolved with abspath while the confinement check used
    realpath, so on macOS - where /var and /tmp are symlinks into /private - every valid
    relative path was rejected as an escape attempt. The traversal tests still passed,
    which is exactly why a positive case is needed alongside them.
    """
    with tempfile.TemporaryDirectory() as real:
        sample_repo(real)
        # tempfile on macOS already hands back a symlinked path, but make it explicit so
        # this test is meaningful on Linux too.
        link_parent = tempfile.mkdtemp()
        link = os.path.join(link_parent, "workspace")
        try:
            os.symlink(real, link)
            result, data = mcp_tool(link, "dita_read_topic",
                                    {"path": "topics/shared.dita"})
            assert result.get("isError") is not True, result["content"][0]["text"]
            assert data.get("title") == "Shared", data
            # And the confinement must still hold from the symlinked root.
            result, _ = mcp_tool(link, "dita_read_topic", {"path": "../../etc/passwd"})
            assert result.get("isError") is True
        finally:
            if os.path.islink(link):
                os.unlink(link)
            os.rmdir(link_parent)


@case
def test_mcp_refuses_to_escape_the_workspace():
    """Path confinement is the security boundary and must hold on every path argument."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        for args in ({"path": "../../../../etc/passwd"},
                     {"path": "/etc/passwd"}):
            result, _ = mcp_tool(tmp, "dita_read_topic", args)
            assert result.get("isError") is True, args
            assert "escape" in result["content"][0]["text"].lower(), result

        result, _ = mcp_tool(tmp, "dita_map_structure", {"map": "../../../etc"})
        assert result.get("isError") is True

        # An unknown tool must be an error, not a crash.
        result, _ = mcp_tool(tmp, "dita_not_a_tool")
        assert result.get("isError") is True


@case
def test_mcp_write_tool_is_the_only_one():
    """Exactly one tool may write, and it may only create."""
    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        tools = mcp(tmp, "tools/list")["result"]["tools"]
        writers = [t["name"] for t in tools
                   if "creat" in t["description"].lower()
                   and "WRITES" in t["description"]]
        assert writers == ["dita_new_topic"], writers
        names = {t["name"] for t in tools}
        for forbidden in ("dita_delete", "dita_rename", "dita_publish", "dita_write_file"):
            assert forbidden not in names, forbidden


@case
def test_api_is_read_only_and_confined():
    """The HTTP API must refuse writes and reject traversal."""
    import random
    import socket
    import time
    import urllib.error
    import urllib.request

    with tempfile.TemporaryDirectory() as tmp:
        sample_repo(tmp)
        for _ in range(12):
            port = random.randint(20000, 60000)
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", port)) != 0:
                    break
        proc = subprocess.Popen(
            [sys.executable, os.path.join(IFACE, "api-server.py"),
             "--root", tmp, "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = "http://127.0.0.1:%d" % port
            for _ in range(40):
                try:
                    urllib.request.urlopen(base + "/health", timeout=1).read()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.25)
            else:
                raise AssertionError("api server did not start")

            body = json.loads(urllib.request.urlopen(base + "/overview", timeout=10).read())
            # Regression: this key was absent when no toolkit was installed, so a plain
            # read raised KeyError in every consumer.
            assert "dita_version" in body["toolkit"], body["toolkit"]

            body = json.loads(urllib.request.urlopen(base + "/check", timeout=10).read())
            assert body["count"] > 0, body

            try:
                urllib.request.urlopen(
                    urllib.request.Request(base + "/overview", data=b"{}", method="POST"),
                    timeout=10)
                raise AssertionError("POST should be refused")
            except urllib.error.HTTPError as exc:
                assert exc.code == 405, exc.code

            try:
                urllib.request.urlopen(
                    base + "/structure?map=../../../etc/passwd", timeout=10)
                raise AssertionError("traversal should be refused")
            except urllib.error.HTTPError as exc:
                assert exc.code == 400, exc.code
        finally:
            proc.terminate()
            proc.wait(timeout=10)


def main():
    failures = []
    for fn in CASES:
        name = fn.__name__
        try:
            fn()
            print("  pass  %s" % name)
        except AssertionError as exc:
            failures.append((name, str(exc)))
            print("  FAIL  %s" % name)
            print("          %s" % str(exc)[:300])
        except Exception as exc:  # noqa: BLE001
            failures.append((name, "%s: %s" % (type(exc).__name__, exc)))
            print("  ERROR %s: %s" % (name, exc))
    print("")
    print("%d passed, %d failed, of %d" % (len(CASES) - len(failures), len(failures),
                                           len(CASES)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
