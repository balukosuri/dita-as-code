#!/usr/bin/env bash
# Install the DITA-as-Code Kit as a user-scope agent skill.
#
# Symlinks rather than copies, deliberately: a copied skill freezes at its current version
# and silently stops tracking the clone, which is a confusing failure to debug six months
# later when a vendor pack has been corrected upstream.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="dita-as-code"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ -f "$SRC/SKILL.md" ]] || die "SKILL.md not found next to this script. Run it from the clone."

python3 --version >/dev/null 2>&1 || die "python3 is required (3.8 or later)."

installed=0
for base in "$HOME/.cursor/skills" "$HOME/.claude/skills"; do
  parent="$(dirname "$base")"
  [[ -d "$parent" ]] || continue
  mkdir -p "$base"
  target="$base/$NAME"
  if [[ -L "$target" ]]; then
    current="$(readlink "$target")"
    if [[ "$current" == "$SRC" ]]; then
      echo "already linked: $target"
      installed=$((installed + 1))
      continue
    fi
    echo "replacing existing link: $target -> $current"
    rm "$target"
  elif [[ -e "$target" ]]; then
    die "$target exists and is not a symlink. Move it aside first - refusing to delete
something this script did not create."
  fi
  ln -s "$SRC" "$target"
  echo "linked: $target -> $SRC"
  installed=$((installed + 1))
done

[[ $installed -gt 0 ]] || die "found neither ~/.cursor nor ~/.claude. Install Cursor or Claude
Code first, or point your agent at $SRC/SKILL.md directly."

echo ""
echo "Verifying:"
test -f "$SRC/scripts/detect.py" && echo "  scripts   ok"
test -d "$SRC/packs" && echo "  packs     ok ($(find "$SRC/packs" -name '*.yml' | wc -l | tr -d ' ') vendor packs)"
test -d "$SRC/templates" && echo "  templates ok"
test -d "$SRC/references" && echo "  refs      ok"

echo ""
echo "Self-test:"
python3 "$SRC/fixtures/test_detection.py" 2>&1 | tail -2

cat <<'EOF'

Installed. Restart your agent, then try:

    dita as code                 audit, then one-shot setup
    dac audit                    read-only audit, changes nothing

Or run it directly without an agent:

    python3 scripts/dac.py audit --root /path/to/your/docs
EOF
