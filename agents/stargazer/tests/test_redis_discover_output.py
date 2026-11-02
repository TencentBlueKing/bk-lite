"""Redis 发现脚本把算出来的安装路径写进采集结果。"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "plugins/inputs/redis/redis_default_discover.sh",
    ROOT / "tests/collect_fixtures/init/redis_default_discover.sh",
    ROOT / "tests/collect_fixtures/init/redis_sentinel_default_discover.sh",
]


def test_emit_writes_computed_install_path():
    for script in SCRIPTS:
        command = f"""
set -eu
eval "$(sed '/^main "$@"$/d' '{script}')"
emit_instance "10.0.0.8" "6379" "standalone" "master" "7.4.9" "/usr/bin/redis-server" "10000" "0" "cluster-1" "[]" "{{}}"
emit_partial_instance "10.0.0.8" "6380" "6.2.1" "/usr/local/bin/redis-server"
"""
        completed = subprocess.run(["sh", "-c", command], check=True, capture_output=True, text=True)
        lines = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        assert lines[0]["install_path"] == "/usr/bin/redis-server"
        assert lines[0]["version"] == "7.4.9"
        assert lines[1]["install_path"] == "/usr/local/bin/redis-server"
        assert lines[1]["version"] == "6.2.1"
