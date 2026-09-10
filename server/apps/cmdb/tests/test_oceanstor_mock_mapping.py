# -*- coding: utf-8 -*-
"""用 DeviceManager mock 夹具跑 CMDB 映射：空 MAC/WWPN 跳过，contains 边只写有身份的口。"""
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
STARGAZER_ROOT = REPO_ROOT / "agents" / "stargazer"
if str(STARGAZER_ROOT) not in sys.path:
    sys.path.insert(0, str(STARGAZER_ROOT))

STORAGE_NAME = "华为存储-127.0.0.1"


def _mock_api():
    from devtools.oceanstor_mock.server import DEFAULT_DEVICE_ID, collect_result_from_fixtures, to_vm_vector

    return DEFAULT_DEVICE_ID, collect_result_from_fixtures, to_vm_vector


def _make_runner(monkeypatch, inst_name=STORAGE_NAME):
    from apps.cmdb.collection.collect_plugin.oceanstor import OceanStorCollectMetrics
    from apps.cmdb.collection.plugins.community.cloud.oceanstor import OceanStorCollectionPlugin

    class _FakeInst:
        model_id = "storage"
        instances = [{"inst_name": inst_name}]

    monkeypatch.setattr(OceanStorCollectMetrics, "get_collect_inst", lambda self: _FakeInst())
    return OceanStorCollectionPlugin(inst_name=inst_name, inst_id=1, task_id=9401)


def _map_mock_fixtures(monkeypatch):
    device_id, collect_result_from_fixtures, to_vm_vector = _mock_api()
    runner = _make_runner(monkeypatch)
    collect_result = collect_result_from_fixtures(host="127.0.0.1", device_id=device_id)
    runner.format_data(to_vm_vector(collect_result, timestamp=int(time.time()) - 60))
    runner.format_metrics()
    return runner, collect_result


def test_mock_fixtures_keep_empty_mac_and_wwpn_in_raw_collect():
    _device_id, collect_result_from_fixtures, _to_vm_vector = _mock_api()
    collect_result = collect_result_from_fixtures()
    eth_ports = collect_result["storage_eth_port"]
    fc_ports = collect_result["storage_fc_port"]
    assert [item.get("MACADDR") for item in eth_ports] == ["AA-BB-CC-DD-EE-01", "", None]
    assert eth_ports[2]["MACADDRESS"] == "AA-BB-CC-DD-EE-02"
    assert [item.get("WWPN") for item in fc_ports] == ["21000024FF5A1234", "--", None]
    assert fc_ports[2]["WWN"] == "21000024FF5A1235"
    empty_eth = eth_ports[1]
    empty_fc = fc_ports[1]
    assert empty_eth["MACADDR"] == ""
    assert empty_eth.get("MACADDRESS") in (None, "")
    assert empty_fc["WWPN"] == "--"
    assert empty_fc.get("WWN") in (None, "")


def test_mock_eth_port_skips_empty_mac_and_writes_contains(monkeypatch):
    runner, _collect = _map_mock_fixtures(monkeypatch)
    ports = runner.result["storage_eth_port"]
    assert [item["inst_name"] for item in ports] == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"]
    assert all(item["mac"] for item in ports)
    assert "CTE0.A.IOM0.P1" not in [item["inst_name"] for item in ports]
    eth = ports[0]
    assert eth["mac"] == "aa:bb:cc:dd:ee:01"
    assert eth["name"] == "CTE0.A.IOM0.P0"
    assert eth["location"] == "CTE0.A.IOM0.P0"
    assert eth["ip_addr"] == "10.0.1.8"
    assert eth["assos"] == [
        {
            "model_id": "storage",
            "inst_name": STORAGE_NAME,
            "asst_id": "contains",
            "model_asst_id": "storage_contains_storage_eth_port",
        }
    ]
    assert all("interface_connect" not in item["model_asst_id"] for item in eth["assos"])


def test_mock_fc_port_skips_empty_wwpn_and_writes_contains(monkeypatch):
    runner, _collect = _map_mock_fixtures(monkeypatch)
    ports = runner.result["storage_fc_port"]
    assert [item["inst_name"] for item in ports] == ["21:00:00:24:ff:5a:12:34", "21:00:00:24:ff:5a:12:35"]
    assert all(item["wwpn"] for item in ports)
    assert "CTE0.A.IOM1.P1" not in [item["inst_name"] for item in ports]
    fc = ports[0]
    assert fc["wwpn"] == "21:00:00:24:ff:5a:12:34"
    assert fc["name"] == "CTE0.A.IOM1.P0"
    assert fc["speed"] == "16"
    assert fc["assos"] == [
        {
            "model_id": "storage",
            "inst_name": STORAGE_NAME,
            "asst_id": "contains",
            "model_asst_id": "storage_contains_storage_fc_port",
        }
    ]


def test_mock_pool_disk_volume_regression(monkeypatch):
    device_id, _collect_result_from_fixtures, _to_vm_vector = _mock_api()
    runner, collect_result = _map_mock_fixtures(monkeypatch)
    storage = runner.result["storage"][0]
    assert storage["inst_name"] == STORAGE_NAME
    assert storage["device_sn"] == device_id
    assert storage["model"] == "Dorado 5000 V6"
    assert storage["firmware_version"] == "V600R003C00"
    assert storage["pool_count"] == 1
    pool = runner.result["storage_pool"][0]
    assert pool["inst_name"] == f"{STORAGE_NAME}/StoragePool001"
    assert pool["total_capacity"] == 1024
    disk = runner.result["storage_disk"][0]
    assert disk["inst_name"] == f"{STORAGE_NAME}/CTE0.0|HSSD-D7K94DN7T6V"
    volume = runner.result["storage_volume"][0]
    assert volume["inst_name"] == f"{STORAGE_NAME}/aSV_Cluster01_LUN001"
    assert collect_result["storage"][0]["total_capacity"] == "1024"


def test_http_mock_session_then_cmdb_mapping_skips_and_contains(monkeypatch):
    import httpx
    from devtools.oceanstor_mock.server import OceanStorMockServer, collect_result_from_fixtures, to_vm_vector

    with OceanStorMockServer(port=0) as server:
        with httpx.Client(timeout=5.0) as client:
            login = client.post(
                f"{server.base_url}/deviceManager/rest/xxxxx/sessions",
                json={"username": server.username, "password": server.password, "scope": "0"},
            )
            data = login.json()["data"]
            token = data["iBaseToken"]
            device_id = data["deviceid"]
            headers = {"iBaseToken": token, "Content-Type": "application/json"}
            fetched = {}
            for path in ("system", "storagepool", "disk", "lun", "eth_port", "fc_port"):
                resp = client.get(
                    f"{server.base_url}/deviceManager/rest/{device_id}/{path}",
                    headers=headers,
                    params={"range": "[0-99]"} if path != "system" else None,
                )
                assert resp.json()["error"]["code"] == 0
                fetched[path] = resp.json()["data"]
            client.delete(f"{server.base_url}/deviceManager/rest/{device_id}/sessions", headers=headers)

    expected = collect_result_from_fixtures(host=server.host, device_id=device_id)
    assert fetched["eth_port"] == expected["storage_eth_port"]
    assert fetched["fc_port"] == expected["storage_fc_port"]
    assert fetched["system"]["PRODUCTMODESTRING"] == "Dorado 5000 V6"

    collect_result = {
        "storage": expected["storage"],
        "storage_pool": fetched["storagepool"],
        "storage_disk": fetched["disk"],
        "storage_volume": fetched["lun"],
        "storage_eth_port": fetched["eth_port"],
        "storage_fc_port": fetched["fc_port"],
    }
    runner = _make_runner(monkeypatch)
    runner.format_data(to_vm_vector(collect_result, timestamp=int(time.time()) - 60))
    runner.format_metrics()
    assert [item["inst_name"] for item in runner.result["storage_eth_port"]] == ["aa:bb:cc:dd:ee:01", "aa:bb:cc:dd:ee:02"]
    assert [item["inst_name"] for item in runner.result["storage_fc_port"]] == ["21:00:00:24:ff:5a:12:34", "21:00:00:24:ff:5a:12:35"]
    assert runner.result["storage_eth_port"][0]["assos"][0]["model_asst_id"] == "storage_contains_storage_eth_port"
    assert runner.result["storage_fc_port"][0]["assos"][0]["model_asst_id"] == "storage_contains_storage_fc_port"
