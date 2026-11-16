#!/bin/sh
set -eu
root=/opt/bklite-environment-test-20261113
here=$root/runtime/business
exec 9>"$root/business-reconcile.lock"
flock -n 9
test -f "$here/Ansible-Executor.json"
test -f "$here/system.yaml"
python3 "$here/reconcile.py" --plan
python3 "$here/reconcile.py" --apply
cp "$here/system.yaml" "$root/business-20261115/system.yaml"
docker compose -f "$here/compose.yaml" up -d --pull never
printf '__ISOLATED_BUSINESS_DEPLOYMENT_RECONCILED__\n'
