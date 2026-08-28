"""plugin.yml target_policy → 预检 kind 覆盖。"""

from __future__ import annotations

import pytest
from core.collection.request_builder import build_collection_request
from core.collection.yaml_target_policy import apply_executor_target_policy, apply_yaml_target_policy, apply_yaml_target_policy_async
from core.plugin.yaml_reader import ExecutorConfig, PluginYamlReader


@pytest.fixture
def reader():
    return PluginYamlReader(plugins_base_dir="plugins/inputs")


def test_host_yaml_policy_overrides_builder_guess(reader):
    request = build_collection_request(
        task_id="yaml-host",
        params={
            "model_id": "host",
            "executor_type": "job",
            "host": "172.19.0.20",
            "node_id": "node-1",
        },
    )
    # builder 兜底可能是 remote；yaml 再确认并写入 mode
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "remote"
    assert enriched.params["target_policy_mode"] == "remote_channel"


def test_network_yaml_policy_is_snmp(reader):
    request = build_collection_request(
        task_id="yaml-snmp",
        params={
            "model_id": "network",
            "executor_type": "protocol",
            "host": "10.10.69.245",
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "snmp"
    assert enriched.params["target_policy_mode"] == "snmp"
    assert int(enriched.params["port"]) == 161


def test_final_fallback_executor_policy_overrides_initial_enterprise_policy():
    request = build_collection_request(
        task_id="yaml-fallback",
        params={
            "model_id": "network",
            "host": "10.10.69.245",
            "preflight_kind": "https",
        },
    )
    fallback = ExecutorConfig(
        executor_type="protocol",
        config={"target_policy": {"mode": "snmp", "port": 161}},
        plugin_config={"metadata": {"type": "network"}},
    )

    enriched = apply_executor_target_policy(request, fallback)

    assert enriched.params["preflight_kind"] == "snmp"
    assert enriched.params["target_policy_mode"] == "snmp"
    assert enriched.params["port"] == 161


@pytest.mark.asyncio
async def test_async_network_yaml_policy_uses_same_contract(reader):
    request = build_collection_request(
        task_id="yaml-snmp-async",
        params={
            "model_id": "network",
            "executor_type": "protocol",
            "host": "10.10.69.245",
        },
    )

    enriched = await apply_yaml_target_policy_async(request, reader=reader)

    assert enriched.params["preflight_kind"] == "snmp"
    assert enriched.params["target_policy_mode"] == "snmp"
    assert int(enriched.params["port"]) == 161


def test_network_config_file_yaml_policy_is_remote_channel(reader):
    request = build_collection_request(
        task_id="yaml-ncf",
        params={
            "model_id": "network_config_file",
            "executor_type": "protocol",
            "host": "10.10.69.10",
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "remote"
    assert enriched.params["target_policy_mode"] == "remote_channel"
    assert int(enriched.params["port"]) == 22


@pytest.mark.parametrize(
    ("os_type", "winrm_scheme", "kind", "port"),
    (
        ("windows", "https", "tcp", 5986),
        ("windows", "http", "tcp", 5985),
        ("macos", "https", "remote", 22),
        ("linux", None, "remote", 22),
    ),
)
def test_pc_preflight_port_refinement(os_type, winrm_scheme, kind, port):
    from core.collection.yaml_target_policy import _refine_pc_preflight

    params = {
        "os_type": os_type,
        "preflight_kind": "remote",
        "target_policy_mode": "remote_channel",
    }
    if winrm_scheme is not None:
        params["winrm_scheme"] = winrm_scheme
    _refine_pc_preflight(params, "pc")
    assert params["preflight_kind"] == kind
    assert int(params["port"]) == port


def test_mysql_protocol_yaml_policy_is_tcp(reader):
    request = build_collection_request(
        task_id="yaml-mysql",
        params={
            "model_id": "mysql",
            "executor_type": "protocol",
            "host": "10.10.24.1",
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "tcp"
    assert enriched.params["target_policy_mode"] == "tcp"
    assert int(enriched.params["port"]) == 3306


def test_mysql_job_yaml_policy_is_remote_channel(reader):
    request = build_collection_request(
        task_id="yaml-mysql-job",
        params={
            "model_id": "mysql",
            "executor_type": "job",
            "host": "10.10.24.1",
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "remote"
    assert enriched.params["target_policy_mode"] == "remote_channel"


@pytest.mark.parametrize(
    ("model_id", "instance_id", "trusted_domain"),
    (
        ("qcloud", "cmdb_8", "tencentcloudapi.com"),
        ("aliyun", "cmdb_7", "aliyuncs.com"),
    ),
)
def test_cloud_yaml_policy_keeps_instance_id_logical(reader, model_id, instance_id, trusted_domain):
    request = build_collection_request(
        task_id=f"yaml-cloud-{model_id}",
        params={"model_id": model_id, "hosts": "", "instance_id": instance_id},
    )

    enriched = apply_yaml_target_policy(request, reader=reader)

    assert enriched.targets == (instance_id,)
    assert enriched.params["target_is_logical"] is True
    assert enriched.params["preflight_kind"] == "cloud"
    assert enriched.params["_yaml_target_policy_verified"] is True
    assert enriched.params["trusted_endpoint_domains"] == (trusted_domain,)


@pytest.mark.parametrize("model_id", ("sangforscp", "sangforhci"))
def test_sangfor_platform_yaml_policy_is_https_tls(reader, model_id):
    if not reader.resolver.is_enterprise_available():
        pytest.skip("enterprise plugins unavailable")
    try:
        reader.get_plugin_resolution(model_id, prefer_enterprise=True)
    except Exception:
        pytest.skip(f"enterprise plugin {model_id} unavailable")

    request = build_collection_request(
        task_id=f"yaml-{model_id}",
        params={
            "model_id": model_id,
            "executor_type": "protocol",
            "host": "10.20.0.10",
            "port": 443,
            "prefer_enterprise": True,
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "https"
    assert enriched.params["target_policy_mode"] == "tls"
    assert int(enriched.params["port"]) == 443
    assert enriched.params["_yaml_target_policy_verified"] is True
