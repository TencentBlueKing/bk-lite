"""plugin.yml target_policy → 预检 kind 覆盖。"""

from __future__ import annotations

import pytest

from core.collection.request_builder import build_collection_request
from core.collection.yaml_target_policy import apply_yaml_target_policy
from core.plugin.yaml_reader import PluginYamlReader


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


def test_network_yaml_policy_is_outbound_only(reader):
    request = build_collection_request(
        task_id="yaml-snmp",
        params={
            "model_id": "network",
            "executor_type": "protocol",
            "host": "10.10.69.245",
        },
    )
    enriched = apply_yaml_target_policy(request, reader=reader)
    assert enriched.params["preflight_kind"] == "outbound_only"
    assert enriched.params["target_policy_mode"] == "outbound_only"
    assert int(enriched.params["port"]) == 161


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
