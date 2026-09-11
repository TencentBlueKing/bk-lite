"""可选真实 Telegraf 时序验收：无网络、只读、有资源上限的临时容器。"""
import os
import re
import subprocess
import uuid

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(os.getenv("CMDB_TELEGRAF_OFFSET_LIVE") != "1", reason="显式启用 Telegraf Docker 时序验收"),
]


def test_telegraf_129_keeps_phase_after_reload_and_restart(tmp_path):
    config = """[agent]
  interval = "10s"
  round_interval = true
  flush_interval = "1s"
  collection_jitter = "0s"
  flush_jitter = "0s"
  omit_hostname = true
[[inputs.exec]]
  commands = ["echo phase,channel=a value=1i"]
  interval = "10s"
  collection_offset = "0s"
  data_format = "influx"
[[inputs.exec]]
  commands = ["echo phase,channel=b value=1i"]
  interval = "10s"
  collection_offset = "5s"
  data_format = "influx"
[[inputs.exec]]
  commands = ["echo phase,channel=c value=1i"]
  interval = "10s"
  data_format = "influx"
[[outputs.file]]
  files = ["stdout"]
  data_format = "influx"
"""
    (tmp_path / "phase.conf").write_text(config)
    # 等待真实样本后才推进阶段；固定 14s 可能早于“下一周期边界 + 5s”。
    script = """set -e
: > /tmp/phase.log
observe_stage() {
  echo "phase_stage=$1 timestamp=$(date +%s)"
  start_line=$(wc -l < /tmp/phase.log)
  attempts=0
  while [ "$attempts" -lt 35 ]; do
    if awk -v start="$start_line" '
      NR > start && /^phase,channel=a / { a++ }
      NR > start && /^phase,channel=b / { b++ }
      NR > start && /^phase,channel=c / { c++ }
      END { exit !(a >= 2 && b >= 2 && c >= 2) }
    ' /tmp/phase.log; then
      awk -v start="$start_line" 'NR > start' /tmp/phase.log
      return 0
    fi
    sleep 1
    attempts=$((attempts + 1))
  done
  cat /tmp/phase.log
  return 1
}
telegraf --config /test/phase.conf >> /tmp/phase.log & child=$!
observe_stage initial
kill -HUP "$child"
observe_stage reload
kill -TERM "$child"
wait "$child"
telegraf --config /test/phase.conf >> /tmp/phase.log & child=$!
observe_stage restart
kill -TERM "$child"
wait "$child"
echo "phase_stage=done timestamp=$(date +%s)"
"""
    name = f"cmdb-offset-test-{uuid.uuid4().hex}"
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=1m",
        "--cpus",
        "0.5",
        "--memory",
        "128m",
        "--pids-limit",
        "64",
        "--entrypoint",
        "/bin/sh",
        "-v",
        f"{tmp_path}:/test:ro",
        "telegraf:1.29.5",
        "-c",
        script,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10, check=False)
    print(result.stdout)
    print(result.stderr)
    assert result.returncode == 0, result.stderr
    phases = re.findall(r"phase_stage=(initial|reload|restart) timestamp=\d+\n(.*?)(?=phase_stage=)", result.stdout, re.DOTALL)
    assert [name for name, _ in phases] == ["initial", "reload", "restart"], result.stdout
    for phase, output in phases:
        events = re.findall(r"phase,channel=([abc]) value=1i (\d+)", output)
        for channel, offset in (("a", 0), ("b", 5), ("c", 0)):
            stamps = [int(timestamp) // 10**9 for role, timestamp in events if role == channel]
            assert len(stamps) >= 2, (phase, channel, stamps)
            assert all(stamp % 10 == offset for stamp in stamps), (phase, channel, stamps)
            assert all(right - left == 10 for left, right in zip(stamps, stamps[1:])), (phase, channel, stamps)
    assert result.stderr.count("Starting Telegraf 1.29.5") >= 3, result.stderr
