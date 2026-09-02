#!/bin/bash
set +e
set +u
set +o pipefail 2>/dev/null || true
export LC_ALL=C
export LANG=C
echo '{'
_first_module=1
# 与 CMDB 主机发现脚本同一套转义，避免依赖目标机解释器。
json_escape() {
  printf '%s' "${1:-}" | awk '
    BEGIN { ORS="" }
    {
      gsub(/\\/, "\\\\")
      gsub(/"/, "\\\"")
      gsub(/\r/, "\\r")
      gsub(/\t/, "\\t")
      if (NR > 1) {
        printf "\\n"
      }
      printf "%s", $0
    }
  '
}
