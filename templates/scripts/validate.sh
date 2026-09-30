#!/usr/bin/env bash
# Validate the documentation before you push.
#
# Four layers, because no single one is sufficient:
#
#   1. Well-formedness  - is it legal XML at all
#   2. Grammar          - does it match the DITA DTD
#   3. References       - do conrefs, keyrefs and links actually resolve
#   4. House rules      - Schematron, if configured
#
# Layer 3 is the one people skip and the one that bites. A GREEN `dita` EXIT CODE IS NOT
# SUFFICIENT EVIDENCE OF REFERENCE INTEGRITY: unresolved conrefs in the PDF preprocess
# stage produced no message at all until a fix closed in July 2023, and keyrefs inside
# conref'd content went unresolved for several releases against the spec's intent. So this
# script greps for the specific diagnostic codes rather than trusting the exit status.

set -uo pipefail

ROOT_MAP="${1:-{{ROOT_MAP}}}"
FAILED=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n==> %s\n' "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; }
pass() { printf 'ok:   %s\n' "$*"; }

[[ -f "$ROOT_MAP" ]] || { echo "error: root map not found: $ROOT_MAP" >&2; exit 2; }

# ---- 1. well-formedness ---------------------------------------------------------------
step "Checking XML well-formedness"
if command -v xmllint >/dev/null 2>&1; then
  if find . -name '*.dita' -o -name '*.ditamap' -o -name '*.ditaval' \
      | grep -v -e '^\./out' -e '^\./temp' \
      | xargs -r xmllint --noout 2>"$TMP/wf.log"; then
    pass "all files are well-formed XML"
  else
    fail "malformed XML found"
    head -20 "$TMP/wf.log" >&2
  fi
else
  echo "skip: xmllint not installed"
fi

# ---- 2 and 3. grammar and references --------------------------------------------------
step "Validating grammar and resolving references"
if command -v dita >/dev/null 2>&1; then
  # --processing-mode=strict promotes warnings that indicate real breakage into failures.
  if dita validate --input="$ROOT_MAP" --processing-mode=strict -v >"$TMP/val.log" 2>&1; then
    pass "dita validate passed"
  else
    fail "dita validate reported errors"
    tail -30 "$TMP/val.log" >&2
  fi

  step "Checking conref, conkeyref and link targets specifically"
  dita --input="$ROOT_MAP" --format=dita --output="$TMP/normalized" -v >"$TMP/refs.log" 2>&1 || true
  if grep -Eq 'DOTJ041E|DOTJ046E|DOTX010E|DOTX028E' "$TMP/refs.log"; then
    fail "broken references found"
    grep -E 'DOTJ041E|DOTJ046E|DOTX010E|DOTX028E' "$TMP/refs.log" | head -20 >&2
  else
    pass "references resolve"
  fi
else
  echo "skip: no local 'dita' command. Run ./scripts/build.sh to use the container instead."
fi

# ---- 4. house rules -------------------------------------------------------------------
step "Checking house rules (Schematron)"
if [[ -f config/schematron/house-rules.sch ]] && [[ -f "${SCHXSLT_JAR:-}" ]]; then
  # -e makes a violation exit non-zero, which is what turns a report into a gate.
  if find . -name '*.dita' | grep -v -e '^\./out' -e '^\./temp' | while read -r f; do
       java -jar "$SCHXSLT_JAR" -d "$f" -s config/schematron/house-rules.sch -e || exit 1
     done; then
    pass "house rules passed"
  else
    fail "house rules violated"
  fi
else
  echo "skip: Schematron not configured, or SCHXSLT_JAR is unset"
fi

printf '\n'
if [[ $FAILED -eq 0 ]]; then
  echo "All checks passed. Safe to push."
else
  echo "Some checks failed. See above - fixing these now is much cheaper than in review." >&2
fi
exit $FAILED
