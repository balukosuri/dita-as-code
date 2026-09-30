# ADR 0001: The CCMS stays the system of record, and Git is a one-way mirror

- **Date:** {{DATE}}
- **Status:** accepted
- **Decided by:** the DITA-as-Code Kit, unattended
- **Reversible:** yes, but not cheaply once people rely on the mirror

## Context

Content is authored in {{CCMS_NAME}}. Setting up docs-as-code around it requires deciding which
system is authoritative when the two disagree.

The decisive constraint is that **no CCMS on the market synchronises DITA source to Git.** Not
Heretto, not MadCap IXIA, not RWS Tridion Docs, not AEM Guides, not Paligo. Paligo's GitHub
integration uploads published output as a zip file. AEM Guides' Git Connector runs the other
way - importing Git into AEM. So there is no vendor-supported two-way sync to adopt; any bridge is
something this project builds and maintains.

## Decision

{{CCMS_NAME}} remains the system of record. A scheduled job exports source one way into this
repository. **Nothing is ever written back.**

Content in this repository is a mirror. Editing it directly will be overwritten by the next sync.

## Alternatives considered

**Two-way synchronisation.** Rejected. Beyond the absence of vendor support, MadCap states
explicitly of IXIA that "the re-import is an overwrite, not a merge." A round trip therefore risks
silently destroying an author's work in the authoritative system. The failure is invisible until
someone notices their content reverted.

**Git as the system of record, with the CCMS demoted to an authoring client.** Rejected for an
unattended run, because it is a workflow change affecting every author and reviewer, not a tooling
change. It is a legitimate destination, but it is a decision for the team to make deliberately.

**No mirror at all.** Rejected. It forgoes automated validation, change history, an independent
build and any disaster-recovery copy - which is most of the value available here.

## Why this one

It is the only option that is safe to set up without a human present. The mirror is additive: if
the sync stops, authoring continues unaffected. Nothing about how anyone writes today changes.

What the team gains without changing their workflow:

- Automated validation and quality gates on every change
- A readable, diffable history of what changed and when
- A build independent of the CCMS, which also reveals version drift between the two
- A recoverable copy of the content outside the vendor's system

What the team does not gain, and should not be promised:

- Pull-request review as an approval gate. Subject-matter experts review in the CCMS UI. The Git
  diff is a visibility surface showing what changed, not a gate on it. This is why the review axis
  in the audit is capped at 2 rather than 4.

## How to change it later

Delete `scripts/sync-from-ccms.sh` and its schedule. Nothing else depends on the direction.

To move to Git as the system of record, treat it as a project rather than a configuration change:
a content freeze, one final export, a decision about what the CCMS is then used for, and retraining
for authors and reviewers.

---

*This decision was made without asking, because the run was unattended. It was chosen as the
conservative option where two paths were both defensible. If it is wrong for your situation,
the section above tells you how to switch - that is the point of recording it rather than
silently picking.*
