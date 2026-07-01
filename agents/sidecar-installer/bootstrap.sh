#!/bin/sh
set -eu

CONFIG_URL="${1:-}"
INSTALL_DIR="${2:-/opt/fusion-collectors}"
INSTALLER_NAME="${3:-bklite-controller-installer}"

if [ -z "$CONFIG_URL" ]; then
  echo "usage: $0 <config_url> [install_dir] [installer_name]" >&2
  exit 1
fi

TMP_DIR="$(mktemp -d)"
INSTALLER_PATH="$TMP_DIR/$INSTALLER_NAME"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT INT TERM

mkdir -p "$INSTALL_DIR"
curl -fsSLk "$CONFIG_URL" -o "$INSTALLER_PATH"
chmod +x "$INSTALLER_PATH"
exec "$INSTALLER_PATH" --url "$CONFIG_URL" --install-dir "$INSTALL_DIR" --skip-tls
