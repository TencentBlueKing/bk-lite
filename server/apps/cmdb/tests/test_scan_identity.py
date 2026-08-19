from types import SimpleNamespace

import pytest

from apps.cmdb.collection.collect_plugin.base import CollectBase
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.scan_identity import NETWORK_CI_TYPES, refine_scan_metrics


class _StubPlugin(CollectBase):
    @property
    def _metrics(self):
        return ["stub_info"]

    def format_data(self, data):
        return data

    def format_metrics(self):
        self.result = {}


def test_collect_base_uses_injected_collect_inst(monkeypatch):
    def _forbidden_get(**kwargs):
        raise AssertionError("scan plugin must not query CollectModels")

    monkeypatch.setattr(CollectModels.objects, "get", _forbidden_get)
    shim = SimpleNamespace(model_id="mysql", instances=[], is_network_topo=False)
    plugin = _StubPlugin("mysql", None, 999, collect_inst=shim)
    assert plugin.get_collect_inst() is shim
    assert plugin.model_id == "mysql"


@pytest.mark.django_db
def test_collect_base_without_collect_inst_still_loads_collect_models():
    task = CollectModels.objects.create(
        name="collect-base-hook",
        task_type="protocol",
        driver_type="protocol",
        model_id="mysql",
        cycle_value_type="cycle",
        team=[1],
    )
    plugin = _StubPlugin("mysql", None, task.id)
    assert plugin.get_collect_inst().id == task.id
    assert plugin.model_id == "mysql"


def test_unknown_soid_is_dropped_from_network_ci():
    result = {
        "switch": [{"inst_name": "10.0.1.11-switch", "ip_addr": "10.0.1.11", "soid": "1.2.3.999"}],
        "interface": [{"inst_name": "10.0.1.11-eth0", "self_device": "10.0.1.11-switch"}],
    }
    refined = refine_scan_metrics("network", result, oid_map={})
    assert refined.get("switch", []) == []
    assert "interface" not in refined


def test_known_switch_soid_is_kept():
    oid = "1.3.6.1.4.1.9.1.1"
    result = {
        "switch": [{"inst_name": "10.0.1.10-switch", "ip_addr": "10.0.1.10", "soid": oid}],
    }
    refined = refine_scan_metrics(
        "network",
        result,
        oid_map={oid: {"device_type": "switch", "oid": oid, "model": "Cisco"}},
    )
    assert len(refined["switch"]) == 1
    assert refined["switch"][0]["ip_addr"] == "10.0.1.10"


def test_non_network_soid_is_not_built_as_switch():
    oid = "1.3.6.1.4.1.2021"
    result = {"switch": [{"inst_name": "10.0.1.12-switch", "ip_addr": "10.0.1.12", "soid": oid}]}
    refined = refine_scan_metrics(
        "network",
        result,
        oid_map={oid: {"device_type": "host", "oid": oid}},
    )
    assert refined.get("switch", []) == []
    assert "host" not in refined


def test_mysql_metrics_pass_through():
    result = {"mysql": [{"inst_name": "10.0.1.20-mysql-3306", "ip_addr": "10.0.1.20", "port": 3306}]}
    refined = refine_scan_metrics("mysql", result)
    assert refined == result


def test_network_ci_types_are_the_four_exact_models():
    assert NETWORK_CI_TYPES == frozenset({"switch", "router", "firewall", "loadbalance"})
