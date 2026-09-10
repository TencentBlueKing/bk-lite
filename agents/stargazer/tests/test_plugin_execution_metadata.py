from pathlib import Path

import pytest
import yaml

PLUGIN_ROOT = Path(__file__).parents[1] / "plugins" / "inputs"
ASYNC_MATRIX_DOCUMENT = Path(__file__).parents[1] / "docs" / "configuration-plugin-async-matrix.md"

EXPECTED_PROTOCOL_EXECUTION_MODES = {
    "aliyun": "sync",
    "fusioninsight": "async",
    "gbase8a": "async",
    "greenplum": "async",
    "hwcloud": "sync",
    "influxdb": "async",
    "ip": "async",
    "kingbase": "async",
    "mssql": "sync",
    "mysql": "async",
    "network": "async",
    "network_config_file": "async",
    "network_topo": "async",
    "dell_unity": "async",
    "netapp_ontap": "async",
    "oceanstor": "async",
    "opengauss": "async",
    "oracle": "async",
    "physcial_server": "sync",
    "postgresql": "async",
    "qcloud": "sync",
    "vastbase": "async",
    "vmware_vc": "sync",
}

CLOUD_AND_VMWARE_COLLECTION_PLUGINS = (
    "aliyun",
    "fusioninsight",
    "hwcloud",
    "qcloud",
    "vmware_vc",
)


@pytest.mark.parametrize(
    "model",
    (
        "fusioninsight",
        "gbase8a",
        "greenplum",
        "influxdb",
        "ip",
        "kingbase",
        "mysql",
        "network",
        "network_config_file",
        "network_topo",
        "dell_unity",
        "netapp_ontap",
        "oceanstor",
        "opengauss",
        "oracle",
        "postgresql",
        "vastbase",
    ),
)
def test_native_protocol_executor_is_declared_async(model):
    config = yaml.safe_load((PLUGIN_ROOT / model / "plugin.yml").read_text(encoding="utf-8"))

    assert config["executors"]["protocol"]["execution_mode"] == "async"


def test_thread_backed_mssql_executor_is_not_declared_native_async():
    config = yaml.safe_load((PLUGIN_ROOT / "mssql" / "plugin.yml").read_text(encoding="utf-8"))

    protocol = config["executors"]["protocol"]
    assert protocol["execution_mode"] == "sync"
    assert protocol["capacity_group"] == "sync_sdk"


def test_network_topology_uses_dedicated_capacity_group():
    config = yaml.safe_load((PLUGIN_ROOT / "network_topo" / "plugin.yml").read_text(encoding="utf-8"))

    assert config["executors"]["protocol"]["capacity_group"] == "network_topology"


@pytest.mark.parametrize(
    "model",
    (
        "fusioninsight",
        "gbase8a",
        "greenplum",
        "influxdb",
        "ip",
        "kingbase",
        "mysql",
        "network_config_file",
        "dell_unity",
        "netapp_ontap",
        "oceanstor",
        "opengauss",
        "oracle",
        "postgresql",
        "vastbase",
    ),
)
def test_native_non_snmp_executor_is_not_classified_as_sync_sdk(model):
    config = yaml.safe_load((PLUGIN_ROOT / model / "plugin.yml").read_text(encoding="utf-8"))

    assert config["executors"]["protocol"]["capacity_group"] == "default"


def test_all_registered_protocol_executors_have_truthful_execution_mode():
    actual = {}
    for config_path in sorted(PLUGIN_ROOT.glob("*/plugin.yml")):
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        protocol = (config.get("executors") or {}).get("protocol")
        if protocol:
            actual[config_path.parent.name] = protocol.get("execution_mode")

    assert actual == EXPECTED_PROTOCOL_EXECUTION_MODES


def test_async_matrix_document_lists_every_registered_plugin():
    document = ASYNC_MATRIX_DOCUMENT.read_text(encoding="utf-8")
    missing = [path.parent.name for path in sorted(PLUGIN_ROOT.glob("*/plugin.yml")) if f"`{path.parent.name}`" not in document]

    assert missing == []


@pytest.mark.parametrize("model", CLOUD_AND_VMWARE_COLLECTION_PLUGINS)
def test_cloud_and_vmware_plugins_have_no_executor_timeout(model):
    config = yaml.safe_load((PLUGIN_ROOT / model / "plugin.yml").read_text(encoding="utf-8"))

    assert "timeout" not in config["executors"]["protocol"]


@pytest.mark.parametrize("model", ("network", "network_topo"))
def test_snmp_plugins_have_no_executor_timeout(model):
    config = yaml.safe_load((PLUGIN_ROOT / model / "plugin.yml").read_text(encoding="utf-8"))

    assert "timeout" not in config["executors"]["protocol"]
