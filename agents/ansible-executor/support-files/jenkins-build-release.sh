#!/usr/bin/env bash
# Shared by fusion-collectors and WeOpsx; build only, never push or deploy.
set -euo pipefail
: "${FUSION_RELEASE_PYTHON:?Set the Python 3.12.15 / OpenSSL 3.5.9 executable}"
: "${DIST:?Set the existing Fusion distribution root}"
: "${WORKSPACE:?Set the Jenkins workspace}"
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
# Both Jenkins Docker context layouts must consume this build, never stale DIST files.
if [ -e "$DIST/linux/ansible-executor-amd64" ]; then
    echo "Refuse existing amd64 output; use a fresh DIST directory" >&2
    exit 1
fi
BUILD_PARENT="$(mktemp -d "${WORKSPACE}/.ansible-release.XXXXXXXX")"
args=(--python "$FUSION_RELEASE_PYTHON" --uv "${FUSION_RELEASE_UV:-uv}"
      --work-dir "$BUILD_PARENT/build" --dist-dir "$DIST/linux")
if [ -n "${FUSION_RELEASE_SOURCES:-}" ]; then
    args+=(--sources-dir "$FUSION_RELEASE_SOURCES")
fi
"$FUSION_RELEASE_PYTHON" "$SOURCE_DIR/build_release.py" "${args[@]}"
"$DIST/linux/ansible-executor/ansible-executor" --verify-release

cp -a "$DIST/linux/ansible-executor" "$DIST/linux/ansible-executor-amd64"
"$DIST/linux/ansible-executor-amd64/ansible-executor" --verify-release
