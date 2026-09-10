import base64
import os
import subprocess
import sys
import time

import pytest
import toml

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models import ChildConfig, CloudRegion, Collector, CollectorConfiguration, Node, NodeCollectorConfiguration, NodeOrganization

pytestmark = pytest.mark.django_db


def create_cmdb_child_config(config_id="cmdb_7", *, node_id="node-1", content=None, operating_system="linux"):
    region = CloudRegion.objects.create(name=f"region-{node_id}")
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip="10.0.0.1",
        operating_system=operating_system,
        cpu_architecture="x86_64",
        collector_configuration_directory="/opt/fusion-collectors/generated",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=1)
    collector = Collector.objects.create(
        id=f"telegraf-{node_id}",
        name="Telegraf",
        service_type="svc",
        node_operating_system=operating_system,
        cpu_architecture="x86_64",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        execute_parameters="",
    )
    parent = CollectorConfiguration.objects.create(
        id=f"parent-{node_id}",
        name=f"parent-{node_id}",
        collector=collector,
        cloud_region=region,
    )
    NodeCollectorConfiguration.objects.create(node=node, collector_config=parent)
    child = ChildConfig.objects.create(
        id=config_id,
        collect_type="http",
        config_type="vmware_vc",
        collector_config=parent,
        content=content
        or """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
  timeout = "30s"
  response_timeout = "30s"
  http_headers = { "cmdbmodel_id" = "vmware_vc" }
  [inputs.prometheus.tags]
    instance_id = "cmdb_7"
    config_type = "vmware_vc"
""",
    )
    return node, child


def test_cmdb_child_config_one_shot_returns_stargazer_acceptance(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, _child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": (
            "prometheus,model_id=vmware_vc,"
            "oneshot_channel_id=cmdb_7,status=accepted,task_id=req-1 "
            "collection_request_accepted=1 1770000000000000000\n"
        ),
        "stderr": "",
    }

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="run-1",
        config_ids=["cmdb_7"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result == {
        "request_id": "run-1",
        "status": "accepted",
        "channels": {
            "cmdb_7": {
                "status": "accepted",
                "task_id": "req-1",
                "retryable": False,
            }
        },
    }


def test_network_one_shot_reports_partial_channel_acceptance(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    ChildConfig.objects.create(
        id="cmdb_7_topology",
        collect_type="http",
        config_type="network_topology",
        collector_config=child.collector_config,
        content=child.content,
    )
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": False,
        "exit_code": 1,
        "stdout": (
            "prometheus,model_id=network,"
            "oneshot_channel_id=cmdb_7,status=accepted,task_id=req-device "
            "collection_request_accepted=1 1770000000000000000\n"
        ),
        "stderr": "input topology received status code 429",
    }

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="run-network",
        config_ids=["cmdb_7", "cmdb_7_topology"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result == {
        "request_id": "run-network",
        "status": "partial",
        "channels": {
            "cmdb_7": {
                "status": "accepted",
                "task_id": "req-device",
                "retryable": False,
            },
            "cmdb_7_topology": {
                "status": "failed",
                "task_id": "",
                "retryable": True,
            },
        },
    }


def test_one_shot_executor_failure_is_retryable_without_leaking_exception(mocker, caplog):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, _child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    error = RuntimeError("password=top-secret token=private-token")
    executor.return_value.execute_local.side_effect = error

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="run-failed",
        config_ids=["cmdb_7"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result == {
        "request_id": "run-failed",
        "status": "failed",
        "channels": {
            "cmdb_7": {
                "status": "failed",
                "task_id": "",
                "retryable": True,
                "error_type": "RuntimeError",
            }
        },
    }
    assert "top-secret" not in repr(result)
    assert "private-token" not in repr(result)
    records = [record for record in caplog.records if "event=telegraf_oneshot_execute_failed" in record.getMessage()]
    assert len(records) == 1
    assert records[0].msg == ("event=telegraf_oneshot_execute_failed request_id=%s node_id=%s failed_stage=execute error_type=%s")
    assert records[0].args == ("run-failed", node.id, "RuntimeError")
    assert records[0].exc_info[2] is error.__traceback__
    assert "top-secret" not in caplog.text
    assert "private-token" not in caplog.text


def test_one_shot_executor_timeout_returns_bounded_retryable_result(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.side_effect = TimeoutError("timed out")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="timeout-run",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result == {
        "request_id": "timeout-run",
        "status": "failed",
        "channels": {
            child.id: {
                "status": "failed",
                "task_id": "",
                "retryable": True,
                "error_type": "TimeoutError",
            }
        },
    }


def test_one_shot_reports_node_lock_contention_without_treating_it_as_collection_failure(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": False,
        "exit_code": 75,
        "stdout": "",
        "stderr": "",
    }

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="lock-busy-run",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result == {
        "request_id": "lock-busy-run",
        "status": "failed",
        "channels": {
            child.id: {
                "status": "failed",
                "task_id": "",
                "retryable": True,
                "error_type": "NodeBusy",
            }
        },
    }


def test_node_mgmt_rpc_interface_runs_saved_child_config(mocker):
    from apps.rpc.node_mgmt import NodeMgmt

    node, _child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": (
            "prometheus,oneshot_channel_id=cmdb_7,status=duplicate_active,task_id=req-rpc collection_request_accepted=1 1770000000000000000\n"
        ),
        "stderr": "",
    }

    result = NodeMgmt(is_local_client=True).run_telegraf_child_configs_once(
        request_id="rpc-run",
        config_ids=["cmdb_7"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "accepted"
    assert result["channels"]["cmdb_7"]["status"] == "duplicate_active"
    assert result["channels"]["cmdb_7"]["task_id"] == "req-rpc"


def test_nats_one_shot_rejects_invalid_or_unsigned_requests(mocker):
    from apps.node_mgmt.nats.node import run_telegraf_child_configs_once

    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    assert run_telegraf_child_configs_once(None)["error_type"] == "InvalidRequest"
    result = run_telegraf_child_configs_once(
        {
            "request_id": "unsigned",
            "config_ids": ["cmdb_7"],
            "expected_node_id": "node-1",
            "organization_ids": [1],
            "authorization": "tampered",
        }
    )

    assert result["error_type"] == "AuthorizationFailed"
    executor.assert_not_called()


def test_one_shot_rejects_node_outside_signed_organization_scope(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="wrong-org",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[2],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_one_shot_uses_controlled_http_config_and_decrypted_env(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    secret = "credential-sentinel"
    content = """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
  interval = "1800s"
  timeout = "60s"
  response_timeout = "30s"
  namedrop = ["collection_request_accepted"]
  http_headers = { "cmdbpassword" = "${PASSWORD_SECRET_cmdb_7}" }
  [inputs.prometheus.tags]
    instance_id = "cmdb_7"
"""
    node, child = create_cmdb_child_config(content=content)
    child.collector_config.env_config = {"STARGAZER_URL": "http://stargazer:8083"}
    child.collector_config.save(update_fields=["env_config"])
    child.env_config = {"PASSWORD_SECRET_cmdb_7": AESCryptor().encode(secret)}
    child.save(update_fields=["env_config"])
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": True,
        "exit_code": 0,
        "stdout": ("prometheus,oneshot_channel_id=cmdb_7,status=accepted,task_id=req-config collection_request_accepted=1 1770000000000000000\n"),
        "stderr": "",
    }

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="config-run",
        config_ids=["cmdb_7"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    execution = executor.return_value.execute_local.call_args
    command = execution.args[0]
    encoded = execution.kwargs["env"][TelegrafOneShotService.CONFIG_ENV_KEY]
    generated = toml.loads(base64.b64decode(encoded).decode("utf-8"))
    http_input = generated["inputs"]["http"][0]
    assert "prometheus" not in generated["inputs"]
    assert http_input["success_status_codes"] == [202]
    assert http_input["data_format"] == "prometheus"
    assert http_input["prometheus_metric_version"] == 2
    assert http_input["timeout"] == "30s"
    assert "response_timeout" not in http_input
    assert "namedrop" not in http_input
    assert http_input["headers"]["cmdbpassword"] == "${PASSWORD_SECRET_cmdb_7}"
    assert http_input["tags"]["oneshot_channel_id"] == "cmdb_7"
    assert generated["outputs"]["file"][0] == {
        "files": ["stdout"],
        "data_format": "influx",
    }
    assert execution.kwargs["env"]["PASSWORD_SECRET_cmdb_7"] == secret
    assert "umask 077" in command
    assert 'mkdir -- "$lock_dir"' in command
    assert "exec 9>" not in command
    assert "ulimit -t 60" in command
    assert "ulimit -v 8388608" in command
    assert "export GOMEMLIMIT=384MiB" in command
    assert "trap cleanup EXIT" in command
    assert 'cat "/proc/$runner_pid/stat"' in command
    assert "runner_is_same" in command
    assert 'if runner_is_same; then kill -KILL "$runner_pid"' in command
    assert "remaining=70" in command
    assert "exec /opt/fusion-collectors/bin/telegraf" in command
    assert encoded not in command
    assert child.content not in command
    assert secret not in repr(result)


def test_one_shot_rejects_wrong_node_without_executing(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="wrong-node",
        config_ids=["cmdb_7"],
        expected_node_id="another-node",
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"]["cmdb_7"]["retryable"] is False
    assert result["channels"]["cmdb_7"]["error_type"] == "TelegrafOneShotError"
    executor.assert_not_called()


def test_one_shot_rejects_mixed_cmdb_task_configs(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    ChildConfig.objects.create(
        id="cmdb_8",
        collect_type="http",
        config_type="vmware_vc",
        collector_config=child.collector_config,
        content=child.content,
    )
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="mixed-tasks",
        config_ids=["cmdb_7", "cmdb_8"],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert set(result["channels"]) == {"cmdb_7", "cmdb_8"}
    assert all(item["retryable"] is False for item in result["channels"].values())
    executor.assert_not_called()


@pytest.mark.parametrize(
    ("collect_type", "content"),
    [
        (
            "http",
            """
[[inputs.http]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
""",
        ),
        (
            "http",
            """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
[[outputs.file]]
  files = ["stdout"]
""",
        ),
        (
            "exec",
            """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
""",
        ),
    ],
)
def test_one_shot_rejects_uncontrolled_child_config(mocker, collect_type, content):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config(content=content)
    child.collect_type = collect_type
    child.save(update_fields=["collect_type"])
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="invalid-child",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_windows_one_shot_is_rejected_until_a_hard_memory_limit_is_available(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config(operating_system="windows")
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="windows-run",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_successful_process_without_acceptance_metric_is_permanent_failure(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": True,
        "result": "unrelated_metric value=1",
        "error": "",
    }

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="missing-acceptance",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id] == {
        "status": "failed",
        "task_id": "",
        "retryable": False,
        "error_type": "AcceptanceMetricMissing",
    }


def test_unsupported_operating_system_returns_structured_permanent_failure(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config(operating_system="darwin")
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="unsupported-os",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    assert result["channels"][child.id]["error_type"] == "TelegrafOneShotError"
    executor.assert_not_called()


def test_repeated_attempts_use_same_bounded_command_without_config_content(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")
    executor.return_value.execute_local.return_value = {
        "success": False,
        "result": "",
        "error": "busy",
    }

    for _attempt in range(2):
        TelegrafOneShotService.run_telegraf_child_configs_once(
            request_id="same-run",
            config_ids=[child.id],
            expected_node_id=node.id,
            organization_ids=[1],
        )

    commands = [call.args[0] for call in executor.return_value.execute_local.call_args_list]
    assert commands[0] == commands[1]


@pytest.mark.parametrize(
    "content",
    [
        """
[agent]
  interval = "1s"
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
""",
        """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
  tags = "not-a-table"
""",
        """
[[inputs.prometheus]]
  urls = ["${STARGAZER_URL}/api/collect/collect_info"]
  http_headers = ["not-a-table"]
""",
    ],
)
def test_one_shot_rejects_unknown_or_malformed_toml_structure(mocker, content):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config(content=content)
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="invalid-structure",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_one_shot_fails_closed_when_region_secret_cannot_be_decrypted(mocker):
    from apps.node_mgmt.models import SidecarEnv
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    SidecarEnv.objects.create(cloud_region_id=node.cloud_region_id, key="PASSWORD_BROKEN", value="not-ciphertext", type="secret")
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="broken-region-secret",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_one_shot_rejects_environment_over_total_byte_limit(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    child.collector_config.env_config = {"OVERSIZED": "x" * TelegrafOneShotService.MAX_ENV_BYTES}
    child.collector_config.save(update_fields=["env_config"])
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="oversized-env",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert result["channels"][child.id]["retryable"] is False
    executor.assert_not_called()


def test_one_shot_rejects_config_count_and_content_size_limits(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    too_many = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="too-many",
        config_ids=[child.id, f"{child.id}_topology", child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )
    child.content += "\n#" + ("x" * TelegrafOneShotService.MAX_CONFIG_BYTES)
    child.save(update_fields=["content"])
    too_large = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="too-large",
        config_ids=[child.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert too_many["status"] == "failed"
    assert too_large["status"] == "failed"
    executor.assert_not_called()


def test_one_shot_rejects_conflicting_child_environments(mocker):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    node, child = create_cmdb_child_config()
    child.env_config = {"CMDB_SCOPE": "device"}
    child.save(update_fields=["env_config"])
    topology = ChildConfig.objects.create(
        id="cmdb_7_topology",
        collect_type="http",
        config_type="network_topology",
        collector_config=child.collector_config,
        content=child.content,
        env_config={"CMDB_SCOPE": "topology"},
    )
    executor = mocker.patch("apps.node_mgmt.services.telegraf_oneshot.Executor")

    result = TelegrafOneShotService.run_telegraf_child_configs_once(
        request_id="conflict",
        config_ids=[child.id, topology.id],
        expected_node_id=node.id,
        organization_ids=[1],
    )

    assert result["status"] == "failed"
    assert all(item["retryable"] is False for item in result["channels"].values())
    executor.assert_not_called()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux one-shot resource boundary")
def test_linux_watchdog_kills_stuck_process_and_cleans_resources(tmp_path, monkeypatch):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    executable = tmp_path / "stuck-telegraf"
    executable.write_text("#!/bin/sh\nexec sleep 120\n", encoding="utf-8")
    executable.chmod(0o700)
    lock_dir = tmp_path / "oneshot.lock"
    temp_template = str(tmp_path / "oneshot.XXXXXX")
    monkeypatch.setattr(TelegrafOneShotService, "LOCK_DIR", str(lock_dir))
    monkeypatch.setattr(TelegrafOneShotService, "TEMP_DIR_TEMPLATE", temp_template)
    monkeypatch.setattr(TelegrafOneShotService, "WATCHDOG_SECONDS", 1)
    command, _shell = TelegrafOneShotService._build_command("linux", str(executable))
    env = dict(os.environ)
    env[TelegrafOneShotService.CONFIG_ENV_KEY] = base64.b64encode(b"[agent]\n").decode("ascii")

    started_at = time.monotonic()
    result = subprocess.run(command, shell=True, executable="/bin/sh", env=env, capture_output=True, timeout=8, check=False)

    assert time.monotonic() - started_at < 6
    assert result.returncode != 0
    assert not lock_dir.exists()
    assert list(tmp_path.glob("oneshot.*")) == []


@pytest.mark.skipif(sys.platform != "linux", reason="Linux /proc process identity boundary")
def test_linux_watchdog_never_signals_a_reused_process_identity(tmp_path, monkeypatch):
    from apps.node_mgmt.services.telegraf_oneshot import TelegrafOneShotService

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    counter = tmp_path / "stat-counter"
    fake_cat = fake_bin / "cat"
    fake_cat.write_text(
        "#!/bin/sh\n"
        f"counter={counter}\n"
        "count=0\n"
        'if [ -f "$counter" ]; then read count < "$counter"; fi\n'
        "count=$((count + 1))\n"
        'printf \'%s\\n\' "$count" > "$counter"\n'
        'if [ "$count" -eq 1 ]; then start=111; else start=222; fi\n'
        "printf '123 (runner) S 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 %s\\n' \"$start\"\n",
        encoding="utf-8",
    )
    fake_cat.chmod(0o700)
    signalled = tmp_path / "signalled"
    executable = tmp_path / "fake-telegraf"
    executable.write_text(
        f"#!/bin/sh\ntrap 'printf signalled > {signalled}; exit 99' TERM\nsleep 1\n",
        encoding="utf-8",
    )
    executable.chmod(0o700)
    lock_dir = tmp_path / "oneshot.lock"
    monkeypatch.setattr(TelegrafOneShotService, "LOCK_DIR", str(lock_dir))
    monkeypatch.setattr(TelegrafOneShotService, "TEMP_DIR_TEMPLATE", str(tmp_path / "oneshot.XXXXXX"))
    monkeypatch.setattr(TelegrafOneShotService, "WATCHDOG_SECONDS", 0)
    command, _shell = TelegrafOneShotService._build_command("linux", str(executable))
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env[TelegrafOneShotService.CONFIG_ENV_KEY] = base64.b64encode(b"[agent]\n").decode("ascii")

    result = subprocess.run(command, shell=True, executable="/bin/sh", env=env, capture_output=True, timeout=5, check=False)

    assert result.returncode == 0
    assert not signalled.exists()
    assert not lock_dir.exists()
    assert list(tmp_path.glob("oneshot.*")) == []
