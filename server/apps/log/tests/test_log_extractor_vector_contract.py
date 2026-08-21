import json
import shutil
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import yaml

from apps.log.services.log_extractor.compiler import compile_system_vector_config
from apps.log.services.log_extractor.semantics import execute_rules, normalize_rule
from apps.log.tests.log_extractor_contract_cases import CONTRACT_CASES


@pytest.mark.unit
@pytest.mark.parametrize("case", CONTRACT_CASES, ids=lambda case: case["name"])
def test_python_preview_uses_shared_contract_cases(case):
    event = {"instance_id": case["name"], **case["event"]}
    expected = {"instance_id": case["name"], **case["expected"]}

    result = execute_rules(event, [normalize_rule(case["draft"])])

    assert result.event == expected
    assert result.results[0].status == case["status"]


@pytest.mark.integration
@pytest.mark.slow
def test_vector_048_runs_shared_contract_cases():
    if not shutil.which("docker"):
        pytest.skip("Docker 不可用")
    records = []
    events = []
    expected = []
    for index, case in enumerate(CONTRACT_CASES):
        records.append(
            SimpleNamespace(
                **{
                    "id": index + 1,
                    "collect_instance_id": case["name"],
                    "sort_order": 0,
                    "target_field": None,
                    **case["draft"],
                }
            )
        )
        events.append({"instance_id": case["name"], **case["event"]})
        expected.append({"instance_id": case["name"], **case["expected"]})
    content = compile_system_vector_config(records)
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "-e",
            "VECTOR_NATS_SERVERS=nats://example:4222",
            "-e",
            "NATS_ADMIN_USERNAME=test",
            "-e",
            "NATS_ADMIN_PASSWORD=test",
            "-e",
            "VECTOR_VICTORIA_LOGS_URL=http://example:9428",
            "--entrypoint",
            "vector",
            "bk-lite.tencentcloudcr.com/bklite/timberio/vector:0.48.0-debian",
            "validate",
            "--no-environment",
            "--config-yaml",
            "/dev/stdin",
        ],
        check=True,
        capture_output=True,
        input=content,
        text=True,
        timeout=120,
    )
    source = yaml.safe_load(content)["transforms"]["log_extractors"]["source"]
    # Vector 在读取完整 YAML 时会把 $$ 还原为 $；vrl 子命令绕过了配置插值，因此测试显式模拟该步骤。
    source = source.replace("$$", "$")
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--entrypoint",
            "vector",
            "bk-lite.tencentcloudcr.com/bklite/timberio/vector:0.48.0-debian",
            "vrl",
            source,
            "--input",
            "/dev/stdin",
            "--print-object",
        ],
        check=False,
        capture_output=True,
        input="".join(json.dumps(event) + "\n" for event in events),
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    actual = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]

    assert actual == expected


@pytest.mark.integration
@pytest.mark.slow
def test_vector_048_moves_legacy_messages_without_retaining_full_copies():
    if not shutil.which("docker"):
        pytest.skip("Docker 不可用")
    config = yaml.safe_load(compile_system_vector_config([]))
    source = config["transforms"]["normalize_event"]["source"].replace("$$", "$")
    # 本用例只校验 message 契约，去掉新增的服务端时间以保持精确断言。
    source += "\ndel(.timestamp)\ndel(.collect_timestamp)"
    events = [
        {"collect_type": "kubernetes", "message": "k8s", "log_message": "k8s"},
        {"collect_type": "winlogbeat", "message": "windows", "_msg": "windows"},
        {"collect_type": "snmp_trap", "message": "raw header", "trap_message": "parsed trap"},
        {"collect_type": "http", "http": {"response": {"code": 200}}},
    ]
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--entrypoint",
            "vector",
            "bk-lite.tencentcloudcr.com/bklite/timberio/vector:0.48.0-debian",
            "vrl",
            source,
            "--input",
            "/dev/stdin",
            "--print-object",
        ],
        check=True,
        capture_output=True,
        input="".join(json.dumps(event) + "\n" for event in events),
        text=True,
        timeout=120,
    )
    actual = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]

    assert actual == [
        {"collect_type": "kubernetes", "message": "k8s"},
        {"collect_type": "winlogbeat", "message": "windows"},
        {"collect_type": "snmp_trap", "message": "parsed trap"},
        {"collect_type": "http", "http": {"response": {"code": 200}}, "message": "Packetbeat HTTP event"},
    ]

    storage_source = config["transforms"]["prepare_victoria_logs"]["source"]
    stored = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--entrypoint",
            "vector",
            "bk-lite.tencentcloudcr.com/bklite/timberio/vector:0.48.0-debian",
            "vrl",
            storage_source,
            "--input",
            "/dev/stdin",
            "--print-object",
        ],
        check=True,
        capture_output=True,
        input=json.dumps({"message": "only once", "host": "node-1"}) + "\n",
        text=True,
        timeout=120,
    )
    stored_events = [json.loads(line) for line in stored.stdout.splitlines() if line.startswith("{")]
    assert stored_events == [{"_msg": "only once", "host": "node-1"}]


@pytest.mark.integration
@pytest.mark.slow
def test_vector_048_uses_central_receive_time_and_preserves_upstream_timestamp():
    if not shutil.which("docker"):
        pytest.skip("Docker 不可用")
    config = yaml.safe_load(compile_system_vector_config([]))
    source = config["transforms"]["normalize_event"]["source"].replace("$$", "$")
    # `vector vrl --print-object` 使用 t'...' 展示原生 timestamp；转换为 sink JSON
    # 中可观察到的 RFC3339 字符串后再由测试解析。
    source += '\n.timestamp = format_timestamp!(.timestamp, format: "%+")'
    events = [
        {"message": "syslog", "timestamp": "2026-08-18T08:00:00+08:00"},
        {
            "message": "already-normalized",
            "timestamp": "2026-08-18T00:01:00Z",
            "collect_timestamp": "2026-08-17T23:59:00Z",
        },
        {"message": "missing"},
        {"message": "invalid", "timestamp": "not-a-time", "@timestamp": "2026-08-18T00:00:00Z"},
    ]
    started_at = datetime.now(timezone.utc)
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--entrypoint",
            "vector",
            "bk-lite.tencentcloudcr.com/bklite/timberio/vector:0.48.0-debian",
            "vrl",
            source,
            "--input",
            "/dev/stdin",
            "--print-object",
        ],
        check=True,
        capture_output=True,
        input="".join(json.dumps(event) + "\n" for event in events),
        text=True,
        timeout=120,
    )
    finished_at = datetime.now(timezone.utc)
    actual = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]

    assert [event.get("collect_timestamp") for event in actual] == [
        "2026-08-18T08:00:00+08:00",
        "2026-08-17T23:59:00Z",
        None,
        "not-a-time",
    ]
    assert actual[3]["@timestamp"] == "2026-08-18T00:00:00Z"
    for event in actual:
        server_timestamp = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert started_at <= server_timestamp <= finished_at
