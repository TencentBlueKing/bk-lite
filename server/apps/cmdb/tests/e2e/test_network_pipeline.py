"""Network 网络设备 SNMP 采集端到端流水线测试 —— network 大类代表。

特点：
  - 走 SNMP 协议而非 SSH/HTTP
  - 通过 sysobjectid 在 OidMapping 表查"设备型号/品牌/类型"
  - device_type 决定 model_id（switch / router / firewall…）
  - inst_name 格式：{ip}-{device_type}
"""
import jsonschema
import pytest

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics


def test_vm_response_matches_schema(load_fixture, load_schema):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")
    schema = load_schema("network/03_vm_metrics.schema.json")
    jsonschema.validate(vm_resp, schema)


@pytest.mark.django_db
def test_network_device_pipeline(load_fixture, monkeypatch):
    vm_resp = load_fixture("network/03_vm_metrics_response.json")

    # 边界拦截
    monkeypatch.setattr(
        "apps.cmdb.collection.query_vm.Collection.query",
        lambda self, sql, timeout=60: vm_resp,
    )

    # OidMapping DB 查询 → 内存替身
    OID_MAP = {
        "1.3.6.1.4.1.9.1.1208": {
            "oid": "1.3.6.1.4.1.9.1.1208",
            "model": "Cisco Catalyst 3850",
            "brand": "Cisco",
            "device_type": "switch",
            "built_in": True,
        }
    }
    monkeypatch.setattr(CollectNetworkMetrics, "get_oid_map", staticmethod(lambda: OID_MAP))

    # 任务对象 + 关掉 topo
    from types import SimpleNamespace
    fake_task = SimpleNamespace(id=7001, is_network_topo=False, instances=[])
    monkeypatch.setattr(CollectNetworkMetrics, "get_collect_inst", lambda self: fake_task)
    monkeypatch.setattr(CollectNetworkMetrics, "model_id", property(lambda self: "network"))

    runner = CollectNetworkMetrics(
        inst_name="snmp-task-01", inst_id=70001, task_id=7001,
    )
    runner.run()

    # 设备类型由 sysobjectid 推导出 "switch" → result["switch"]
    assert "switch" in runner.result
    devices = runner.result["switch"]
    assert len(devices) == 1
    dev = devices[0]
    assert dev["inst_name"] == "10.0.0.1-switch"
    assert dev["ip_addr"] == "10.0.0.1"
    assert dev["brand"] == "Cisco"
    assert dev["model"] == "Cisco Catalyst 3850"


def test_drift_detection_unknown_metric(load_schema):
    bad = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{
                "metric": {"__name__": "some_other_metric", "instance_id": "x", "ip_addr": "1.1.1.1"},
                "value": [1, "1"],
            }],
        },
    }
    schema = load_schema("network/03_vm_metrics.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
