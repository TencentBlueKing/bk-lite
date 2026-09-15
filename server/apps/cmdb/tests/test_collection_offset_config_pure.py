"""三个插件的最终 Telegraf 配置契约。"""
from types import SimpleNamespace

import pytest
import toml

from apps.cmdb.node_configs.config_factory import NodeParamsFactory
from apps.cmdb.node_configs.network.network import NetworkTopoNodeParams

pytestmark = pytest.mark.unit


def task(model_id="host", **overrides):
    values = dict(
        id=91,
        model_id=model_id,
        driver_type="job" if model_id == "host" else "protocol",
        is_interval=True,
        cycle_value_type="cycle",
        cycle_value="30",
        task_type="host" if model_id == "host" else "snmp",
        decrypt_credentials={},
        params={},
        timeout=60,
        access_point=[{"id": "node-1"}],
        instances=[{"ip_addr": "10.0.0.1"}],
        ip_range="",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "model,role,key,seconds,interval",
    [
        ("host", "device", "collection_offset_seconds", 420, "1800s"),
        ("network", "device", "collection_offset_seconds", 660, "1800s"),
        ("network", "topology", "topology_collection_offset_seconds", 1260, "9000s"),
    ],
)
def test_supported_plugin_renders_its_own_offset(model, role, key, seconds, interval):
    instance = task(model, params={"has_network_topo": True, key: seconds, "topology_interval_minutes": 150})
    node = NetworkTopoNodeParams(instance) if role == "topology" else NodeParamsFactory.get_node_params(instance)
    config = toml.loads(node.push_params()[0]["content"])["inputs"]["prometheus"][0]
    assert config["collection_offset"] == f"{seconds}s"
    assert config["interval"] == interval
    assert "collection_offset" not in config["http_headers"]


@pytest.mark.parametrize("value", [None, -60, 1800, "bad", True, 1.5])
def test_invalid_offsets_fall_back_to_zero(value):
    instance = task(params={"collection_offset_seconds": value})
    config = toml.loads(NodeParamsFactory.get_node_params(instance).push_params()[0]["content"])
    assert config["inputs"]["prometheus"][0]["collection_offset"] == "0s"


@pytest.mark.parametrize(
    "model,role,key",
    [
        ("host", "device", "collection_offset_seconds"),
        ("network", "device", "collection_offset_seconds"),
        ("network", "topology", "topology_collection_offset_seconds"),
    ],
)
@pytest.mark.parametrize("include_zero", [False, True], ids=["omitted", "zero"])
def test_supported_plugins_accept_missing_and_zero_offset(model, role, key, include_zero):
    params = {"has_network_topo": True, "topology_interval_minutes": 150}
    if include_zero:
        params[key] = 0
    instance = task(model, params=params)
    node = NetworkTopoNodeParams(instance) if role == "topology" else NodeParamsFactory.get_node_params(instance)
    source = toml.loads(node.push_params()[0]["content"])["inputs"]["prometheus"][0]
    assert source["collection_offset"] == "0s"
    assert source["interval"] == ("9000s" if role == "topology" else "1800s")


def test_other_plugin_does_not_render_offset_even_if_params_contain_it():
    instance = task("redis", params={"collection_offset_seconds": 420})
    node = NodeParamsFactory.get_node_params(instance)
    config = toml.loads(node.push_params()[0]["content"])["inputs"]["prometheus"][0]
    assert "collection_offset" not in config


@pytest.mark.parametrize("model", ["host", "network"])
def test_non_periodic_task_does_not_render_offset(model):
    instance = task(model, is_interval=False, params={"collection_offset_seconds": 420})
    source = toml.loads(NodeParamsFactory.get_node_params(instance).push_params()[0]["content"])["inputs"]["prometheus"][0]
    assert "collection_offset" not in source


@pytest.mark.parametrize("model,plugin", [("redis", "redis_info"), ("mysql", "mysql_info"), ("pc", "pc_info")])
def test_other_plugins_have_no_active_offset_channels(model, plugin):
    from apps.cmdb.services.collection_offset_policy import active_channels, rendered_offset_seconds

    instance = task(model)
    assert active_channels(instance) == []
    assert rendered_offset_seconds(instance, plugin, 1800) is None


@pytest.mark.parametrize(
    "ranges,expected",
    [
        ("10.0.0.1-10.0.0.64", 64),
        ("10.0.0.0/21", 2048),
        ("10.0.0.1,10.0.0.3-10.0.0.4", 3),
        ("node-a.example.com", 1),
        ("10.0.0.9-10.0.0.1", 1),
        ("0.0.0.0/0", 2**32),
        ("", 0),
    ],
)
def test_count_targets_without_expanding_network(ranges, expected):
    from apps.cmdb.services.collection_offset_policy import target_count

    assert target_count(task(instances=[], ip_range=ranges)) == expected


def test_asset_count_takes_precedence_over_range():
    from apps.cmdb.services.collection_offset_policy import target_count

    assert target_count(task(instances=[{}, {}], ip_range="0.0.0.0/0")) == 2
