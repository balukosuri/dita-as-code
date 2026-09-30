#!/usr/bin/env bash
# Build the documentation.
#
# THIS IS THE SAME COMMAND CI RUNS. That is the whole point of the file: when the build
# breaks, "works on my machine" is answerable, because there is only one machine-independent
# path. If you change how the build works, change it here, not in the CI workflow.
#
#   ./scripts/build.sh              build every deliverable
#   ./scripts/build.sh html         build one deliverable by id
#   ./scripts/build.sh --list       show the deliverables defined in the project file
#
# Set DAC_USE_DOCKER=1 to build in a container instead of using a local DITA-OT. That is
# the supported path when you have no Java installed.

set -euo pipefail

PROJECT="config/dita-ot-project.xml"
OUTPUT="${DAC_OUTPUT:-out}"
DITA_OT_VERSION="{{DITA_OT_VERSION}}"
IMAGE="ghcr.io/dita-ot/dita-ot:${DITA_OT_VERSION}"

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

[[ -f "$PROJECT" ]] || die "no $PROJECT found. Run this from the repository root."

# ---------------------------------------------------------------------------------------
# Choose a runtime. Local DITA-OT is preferred because it is faster and because Vale's
# DITA support needs `dita` on PATH anyway.
# ---------------------------------------------------------------------------------------
if [[ "${DAC_USE_DOCKER:-0}" == "1" ]] || ! command -v dita >/dev/null 2>&1; then
  command -v docker >/dev/null 2>&1 \
    || die "no local 'dita' command and no docker. Install Temurin 17 plus DITA-OT ${DITA_OT_VERSION}, or start Docker."
  docker info >/dev/null 2>&1 \
    || die "docker is installed but its daemon is not running. Start Docker Desktop or your container runtime."
  # NOTE: ghcr.io, not ditaot/dita-ot on Docker Hub. That image was abandoned years ago and
  # its newest tag is 2.5.3.
  RUNNER=(docker run --rm -v "$PWD:/src" -w /src "$IMAGE")
  echo "==> building in container $IMAGE"
else
  RUNNER=(dita)
  echo "==> building with local $(dita --version 2>/dev/null | head -1)"

  # DITA files reference public identifiers such as -//OASIS//DTD DITA Map//EN. Without a
  # catalog, validation either fails outright or silently fetches DTDs over HTTP, which is
  # slow, irreproducible, and fails completely on an offline machine.
  if [[ -z "${XML_CATALOG_FILES:-}" ]]; then
    dita_bin="$(command -v dita)"
    dita_home="$(cd "$(dirname "$(readlink "$dita_bin" || echo "$dita_bin")")/.." && pwd)"
    if [[ -f "$dita_home/catalog-dita.xml" ]]; then
      export XML_CATALOG_FILES="$dita_home/catalog-dita.xml"
      echo "==> XML_CATALOG_FILES=$XML_CATALOG_FILES"
    else
      echo "warning: could not locate catalog-dita.xml. DTD resolution may fall back to HTTP." >&2
    fi
  fi
fi

if [[ "${1:-}" == "--list" ]]; then
  "${RUNNER[@]}" deliverables --project="$PROJECT"
  exit 0
fi

# ---------------------------------------------------------------------------------------
# Build. The project file supplies each deliverable's ditaval filter, which is why builds
# go through it rather than through raw --input/--format arguments: a build that omits
# --filter emits conditional content into the wrong output and still exits zero.
# ---------------------------------------------------------------------------------------
if [[ $# -gt 0 ]]; then
  echo "==> building deliverable '$1' into $OUTPUT/"
  "${RUNNER[@]}" --project="$PROJECT" --deliverable="$1" --output="$OUTPUT" -v
else
  echo "==> building all deliverables into $OUTPUT/"
  "${RUNNER[@]}" --project="$PROJECT" --output="$OUTPUT" -v
fi

echo "==> done. Output is in $OUTPUT/"
