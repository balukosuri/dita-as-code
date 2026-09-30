#!/usr/bin/env bash
# Install the DITA toolchain inside the devcontainer.
#
# Pinned on purpose. An unpinned toolkit means CI and the laptop drift apart, and the first
# symptom is usually a formatting difference in published output that nobody can explain.

set -euo pipefail

DITA_OT_VERSION="{{DITA_OT_VERSION}}"
VALE_VERSION="3.22.0"     # floor: DITA ignore patterns need 3.22.0 or later
INSTALL_DIR="/opt"

echo "==> installing DITA-OT ${DITA_OT_VERSION}"
cd "$INSTALL_DIR"
# GitHub releases, not Docker Hub. The Docker Hub image ditaot/dita-ot was abandoned years
# ago with a newest tag of 2.5.3 and its own README warns it will not work as a base.
curl -fsSL -o dita-ot.zip \
  "https://github.com/dita-ot/dita-ot/releases/download/${DITA_OT_VERSION}/dita-ot-${DITA_OT_VERSION}.zip"
unzip -q dita-ot.zip
rm dita-ot.zip
chmod +x "dita-ot-${DITA_OT_VERSION}/bin/dita"

echo "==> installing Vale ${VALE_VERSION}"
curl -fsSL "https://github.com/errata-ai/vale/releases/download/v${VALE_VERSION}/vale_${VALE_VERSION}_Linux_64-bit.tar.gz" \
  | tar xz -C /usr/local/bin vale

echo "==> installing jing for RELAX NG validation"
# jing, not xmllint. xmllint is not a dependable RELAX NG validator, and RNG is what DITA
# 2.0 draft grammars and the DITA-OT project.rnc schema use.
apt-get update -qq && apt-get install -y -qq --no-install-recommends jing libxml2-utils

echo "==> verifying"
"dita-ot-${DITA_OT_VERSION}/bin/dita" --version
vale --version
xmllint --version 2>&1 | head -1

echo "==> installing project npm dependencies"
cd "${CONTAINER_WORKSPACE_FOLDER:-/workspaces}"/* 2>/dev/null || cd /workspaces/*
if [[ -f package.json ]]; then
  npm ci || npm install
fi

echo "==> toolchain ready"
