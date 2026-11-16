#!/usr/bin/env bash
set -euo pipefail
root=/opt/bklite-environment-test-20261113
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec 9>"${root}/query-apply.lock"
flock -n 9
install -m 644 "${source_dir}/query_settings.py" "${root}/runtime/query_settings.py"
install -m 644 "${source_dir}/query_urls.py" "${root}/runtime/query_urls.py"
python3 "${source_dir}/deploy-query.py"
docker exec env-install-ca-api-20261113 python /test/runtime/business/query-fixtures.py
