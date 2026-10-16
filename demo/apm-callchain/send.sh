#!/bin/bash
set -euo pipefail
BASE=${1:-http://127.0.0.1:18080}
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/health" || true)
  if [[ "$code" == "200" ]]; then
    break
  fi
  sleep 0.3
done
curl -s -o /dev/null -w 'book %{http_code}\n' "$BASE/checkout?sku=book"
curl -s -o /dev/null -w 'book %{http_code}\n' "$BASE/checkout?sku=book"
curl -s -o /dev/null -w 'slow %{http_code}\n' --max-time 8 "$BASE/checkout?sku=slow"
curl -s -o /dev/null -w 'fail %{http_code}\n' "$BASE/checkout?sku=fail"
curl -s -o /dev/null -w 'stockout %{http_code}\n' "$BASE/checkout?sku=stockout"
curl -s -o /dev/null -w 'crash %{http_code}\n' "$BASE/checkout?sku=crash"
curl -s -o /dev/null -w 'missing %{http_code}\n' "$BASE/checkout?sku=missing"
curl -s -o /dev/null -w 'not-a-page %{http_code}\n' "$BASE/not-a-page"
