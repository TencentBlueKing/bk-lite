# -*- coding: utf-8 -*-
"""用 Unity mock 夹具跑 CMDB 映射：空 MAC/WWPN 跳过，contains 边只写有身份的口。"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
STARGAZER_ROOT = REPO_ROOT / "agents" / "stargazer"
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

STORAGE_NAME = "Unity-127.0.0.1"


def _mock_api():
    from devtools.dell_unity_mock.server import DEFAULT_SERIAL, collect_result_from_fixtures, to_vm_vector

    return DEFAULT_SERIAL, collect_result_from_fixtures, to_vm_vector


def _make_runner(monkeypatch, inst_name=STORAGE_NAME):
    from apps.cmdb.collection.collect_plugin.dell_unity import DellUnityCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.dell_unity import DellUnityCollectionPlugin

    class _FakeInst:
        model_id = "dell_unity"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(DellUnityCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return DellUnityCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9801)


def _map_mock_fixtures(monkeypatch):
    _device_id, collect_result_from_fixtures, to_vm_vector = _mock_api()
    runner = _make_runner(monkeypatch)
    collect_result = collect_result_from_fixtures(host="127.0.0.1")
    runner.format_data(to_vm_vector(collect_result, timestamp=int(time.time()) - 60))
    runner.format_metrics()
    return runner, collect_result


def test_mock_fixtures_keep_empty_mac_and_wwpn_in_raw_collect():
    _device_id, collect_result_from_fixtures, _to_vm_vector = _mock_api()
    collect_result = collect_result_from_fixtures()
    eth_ports = collect_result["storage_eth_port"]
    fc_ports = collect_result["storage_fc_port"]
    assert [item.get("macAddress") for item in eth_ports] == ["00:60:16:aa:bb:01", "", "00-60-16-AA-BB-02"]
    assert [item.get("wwn") for item in fc_ports] == ["50:06:01:60:88:60:32:8D", "", "500601608860328E"]
    assert all(item.get("wwn") for item in collect_result["storage_volume"])


def test_mock_eth_and_fc_skip_empty_and_write_contains(monkeypatch):
    runner, _collect = _map_mock_fixtures(monkeypatch)
    eth_ports = runner.result["storage_eth_port"]
    assert [item["inst_name"] for item in eth_ports] == ["00:60:16:aa:bb:01", "00:60:16:aa:bb:02"]
    assert eth_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_eth_port"
    assert all("interface_connect" not in item["model_asst_id"] for item in eth_ports[0]["assos"])
    fc_ports = runner.result["storage_fc_port"]
    assert [item["inst_name"] for item in fc_ports] == ["50:06:01:60:88:60:32:8d", "50:06:01:60:88:60:32:8e"]
    assert fc_ports[0]["assos"][0]["model_asst_id"] == "storage_contains_storage_fc_port"


def test_mock_pool_disk_volume_and_storage(monkeypatch):
    device_id, _collect_result_from_fixtures, _to_vm_vector = _mock_api()
    runner, collect_result = _map_mock_fixtures(monkeypatch)
    storage = runner.result["storage"][0]
    assert storage["inst_name"] == STORAGE_NAME
    assert storage["device_sn"] == device_id
    assert storage["brand"] == "dell"
    assert storage["model"] == "Unity 480"
    assert runner.result["storage_pool"][0]["inst_name"] == f"{STORAGE_NAME}/Pool0"
    assert runner.result["storage_disk"][0]["disk_sn"] == "5002538E00000001"
    names = [item["inst_name"] for item in runner.result["storage_volume"]]
    assert f"{STORAGE_NAME}/lun1" in names
    assert collect_result["storage"][0]["total_capacity"] == "1024"
