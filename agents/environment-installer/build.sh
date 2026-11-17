#!/bin/sh
set -eu
: "${SIGNING_PUBLIC_KEY:?Set the base64 Ed25519 release public key}"
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output_dir=${OUTPUT_DIR:-"$source_dir/dist"}
mkdir -p "$output_dir"
output_dir=$(CDPATH= cd -- "$output_dir" && pwd)
cd "$source_dir"
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags "-s -w -X main.trustedSigningKey=$SIGNING_PUBLIC_KEY" -o "$output_dir/environment-entry" .
cd "$source_dir/../sidecar-installer"
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags '-s -w' -o "$output_dir/setup-worker" .
