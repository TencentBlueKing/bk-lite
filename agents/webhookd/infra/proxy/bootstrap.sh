#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

# Colors
R='\033[0;31m' G='\033[0;32m' B='\033[0;34m' N='\033[0m'
log() { echo -e "${2}[$(date +%H:%M:%S)] $1${N}"; }
info() { log "$1" "$B"; }
ok() { log "$1" "$G"; }
err() { log "$1" "$R"; exit 1; }

# Load env
[ -f .env ] || err ".env not found"
set -a; source .env; set +a

# Detect docker compose
if command -v docker-compose &>/dev/null; then
    DC="docker-compose"
elif docker compose version &>/dev/null; then
    DC="docker compose"
else
    err "docker compose not found"
fi

# Start
info "Starting services..."
$DC up -d || err "Failed to start"

# Wait and check
sleep 3
info "Checking services..."
$DC ps --format "table {{.Name}}\t{{.State}}" 2>/dev/null | tail -n +2 | while read -r line; do
    name=$(echo "$line" | awk '{print $1}')
    state=$(echo "$line" | awk '{print $NF}')
    [[ "$state" =~ ^(running|Up)$ ]] && ok "$name: $state" || err "$name: $state"
done

ok "Done"
