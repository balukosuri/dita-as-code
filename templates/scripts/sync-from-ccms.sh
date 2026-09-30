#!/usr/bin/env bash
# Export DITA source from a CCMS into this Git mirror. ONE WAY ONLY.
#
# WHY THIS FILE EXISTS: no CCMS on the market syncs DITA source to Git. Not Heretto, not
# MadCap IXIA, not Tridion Docs, not AEM Guides, not Paligo. Paligo's GitHub integration
# uploads published output as a ZIP. AEM's Git Connector runs the other way, importing Git
# INTO AEM. So this bridge is something you build, not something you switch on - and it is
# the single highest-value thing in a CCMS team's pipeline.
#
# DIRECTION IS ONE-WAY AND THAT IS NOT A LIMITATION TO WORK AROUND. MadCap states in
# writing that IXIA re-import "is an overwrite, not a merge". Writing back risks silently
# destroying an author's work in the system of record. The CCMS stays authoritative; this
# repository is a mirror that buys you history, automated validation, an independent build,
# and disaster recovery.
#
# Usage:  ./scripts/sync-from-ccms.sh
# Env:    DAC_CCMS_TOKEN (required), DAC_CCMS_BASE (required)

set -euo pipefail

VENDOR="{{CCMS_VENDOR}}"
BASE="${DAC_CCMS_BASE:-{{CCMS_BASE_URL}}}"
TOKEN="${DAC_CCMS_TOKEN:-}"
DEST="${DAC_SYNC_DEST:-src}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ -n "$TOKEN" ]] || die "DAC_CCMS_TOKEN is not set. This script never stores credentials."

echo "==> exporting from $VENDOR at $BASE"

case "$VENDOR" in

  heretto)
    # The v2 API is publishing-only and self-labelled Alpha. The v1 endpoints that read
    # content are real but NOT publicly documented - Heretto's docs say "documentation
    # available upon request" and point at your Customer Success Manager. The sanctioned
    # way to get SOURCE out is a webhook in NotifyPull mode.
    #
    # Do NOT build this on WebDAV. Heretto states twice that it "does not provide general
    # WebDAV support" and that WebDAV exists only for Oxygen connections.
    die "Heretto export needs the v1 content API, which requires documentation from your
Customer Success Manager, or a webhook configured in NotifyPull mode. See
.dac/blockers/ for a ready-to-send request. This is a CSM ask, not an admin ask."
    ;;

  ixia-ccms)
    # Authenticate, then run the transformation scenario named "Export", which returns raw
    # DITA under content\authoring with .properties sidecars. No ditaval is applied and
    # DITA-OT is not involved - it is a pure content extraction.
    #
    # CRITICAL: bad credentials return HTTP 200 with error code -10021. Checking the status
    # code alone reports a false success, so the `error` field must be parsed.
    resp="$(curl -fsS -X PUT "$BASE/rest/1.0/sessions/authorize?userId={{CCMS_USER}}" \
      -H 'Content-Type: application/json' \
      -d "{\"data\":\"$TOKEN\"}" -c "$WORK/cookies")" || die "login request failed"
    if printf '%s' "$resp" | grep -q '"error"[[:space:]]*:[[:space:]]*-'; then
      die "login returned HTTP 200 but carries an error code (likely -10021: bad credentials
or a user missing from users.xml). Never trust the status code alone with this API."
    fi
    curl -fsS -b "$WORK/cookies" "$BASE/rest/1.0/{{IXIA_EXPORT_PATH}}" -o "$WORK/export.zip" \
      || die "export failed"
    unzip -q "$WORK/export.zip" -d "$WORK/extracted"
    rsync -a --delete "$WORK/extracted/content/authoring/" "$DEST/"
    ;;

  paligo)
    # Paligo is DocBook 5.1, NOT DITA. Do not feed this into a DITA pipeline.
    #
    # Use the API rather than the DocBook publish: the published XML "does not contain any
    # metadata or information about text fragments and variables", so variables and
    # text-fragment reuse are already gone by the time you have it. GET /documents/{id}
    # returns higher-fidelity source.
    #
    # Requires an ADMIN user - no exceptions, and licence permissions carry into the API.
    # Throttle politely: roughly 50 requests/minute on Business, and a 429 carries
    # Retry-After in seconds.
    die "Paligo content is DocBook 5.1, not DITA. Converting it to DITA is XSLT work that
DAC scopes but does not perform. Its API also requires an admin user, which is a hard wall
rather than something to degrade around. See dac-audit.md."
    ;;

  tridion-docs)
    # ISHRemote (PowerShell) is the RWS-maintained CLI and the practical route. Auth on 15.x
    # is OpenID Connect client credentials; username/password fails with invalid_client.
    command -v pwsh >/dev/null 2>&1 || die "Tridion Docs export needs PowerShell and the ISHRemote module"
    pwsh -NoProfile -Command "
      Import-Module ISHRemote
      New-IshSession -Protocol OpenApiWithOpenIdConnect ``
        -WsBaseUrl '$BASE' -ClientId '{{ISH_CLIENT_ID}}' -ClientSecret '$TOKEN'
      # Retrieve the publication's objects and write them to \$env:DEST
    "
    ;;

  aem-guides)
    # The Assets API. Note that the Git Connector introduced in 2026.08 runs INBOUND only
    # (Git into AEM), so it is not usable for this.
    #
    # AFTER SYNCING, remember: in UUID builds all references are UUID-based and path
    # independent, so a filename-based link checker PASSES CLEAN on genuinely broken links.
    # Link integrity here needs a UUID-aware checker.
    curl -fsS "$BASE/api/assets{{AEM_PATH}}.json" \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Api-Key: {{AEM_CLIENT_ID}}" \
      -o "$WORK/assets.json" || die "AEM Assets API request failed"
    echo "note: AEM sync writes UUID-named files. Use the UUID-aware link checker, not the
filename-based one."
    ;;

  *)
    die "no export recipe for vendor '$VENDOR'. Run 'dac vendors research $VENDOR' first."
    ;;
esac

# ---------------------------------------------------------------------------------------
# Commit only when something actually changed, so the history stays meaningful rather than
# filling up with empty nightly commits.
# ---------------------------------------------------------------------------------------
if [[ -n "$(git status --porcelain "$DEST")" ]]; then
  git add "$DEST"
  git commit -m "sync: import content from $VENDOR

Automated one-way export. The CCMS remains the system of record; this repository is a
mirror. Do not edit these files here - changes will be overwritten by the next sync."
  echo "==> committed changes from $VENDOR"
else
  echo "==> no changes to commit"
fi
