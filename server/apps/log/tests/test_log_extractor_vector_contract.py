import json
import shutil
import subprocess
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
        check=True,
        capture_output=True,
        input="".join(json.dumps(event) + "\n" for event in events),
        text=True,
        timeout=120,
    )
    actual = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]

    assert actual == expected
