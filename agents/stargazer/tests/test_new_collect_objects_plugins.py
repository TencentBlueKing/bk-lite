import importlib
import re
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_plugin(model_id):
    return yaml.safe_load((ROOT / "enterprise" / "plugins" / "inputs" / model_id / "plugin.yml").read_text())


def test_batch1_plugin_manifests_have_expected_defaults():
    expected = {
        "nacos": ("middleware", "protocol", "enterprise.plugins.inputs.nacos.nacos_info", "NacosInfo"),
        "ibmmq": ("middleware", "job", "plugins.script_executor", "SSHPlugin"),
        "oceanbase": ("database", "protocol", "enterprise.plugins.inputs.oceanbase.oceanbase_info", "OceanBaseInfo"),
        "highgo": ("database", "protocol", "enterprise.plugins.inputs.highgo.highgo_info", "HighGoInfo"),
        "server_bmc": ("host_manage", "protocol", "enterprise.plugins.inputs.server_bmc.server_bmc_info", "ServerBmcInfo"),
    }

    for model_id, (category, default_executor, module, class_name) in expected.items():
        plugin = load_plugin(model_id)
        assert plugin["metadata"]["model_id"] == model_id
        assert plugin["category"] == category
        assert plugin["default_executor"] == default_executor
        executor = plugin["executors"][default_executor]
        assert executor["collector"]["module"] == module
        assert executor["collector"]["class"] == class_name


def test_ibmmq_job_uses_read_only_discovery_script():
    plugin = load_plugin("ibmmq")
    script = plugin["executors"]["job"]["scripts"]["linux"]
    assert script == "enterprise/plugins/inputs/ibmmq/ibmmq_default_discover.sh"

    body = (ROOT / script).read_text()
    assert "dspmq" in body
    assert "dspmqver" in body
    assert "runmqsc" in body
    assert "qmgr_name" in body
    # SSHPlugin 目前只按 model_id 包装 JSON 行，ibmmq 子模型拆分留给 Task 6 formatter adapter。
    assert re.search(r"\bdis(play)?\b", body, re.IGNORECASE)
    assert not re.search(r"\b(start|stop|delete|change|reset|endmqm|strmqm)\b", body, re.IGNORECASE)


def test_protocol_collectors_are_importable():
    imports = {
        "enterprise.plugins.inputs.nacos.nacos_info": "NacosInfo",
        "enterprise.plugins.inputs.oceanbase.oceanbase_info": "OceanBaseInfo",
        "enterprise.plugins.inputs.highgo.highgo_info": "HighGoInfo",
        "enterprise.plugins.inputs.server_bmc.server_bmc_info": "ServerBmcInfo",
    }
    for module_name, class_name in imports.items():
        module = importlib.import_module(module_name)
        assert hasattr(module, class_name)


def test_server_bmc_collector_returns_formatter_keys(monkeypatch):
    from enterprise.plugins.inputs.server_bmc.server_bmc_info import ServerBmcInfo

    collector = object.__new__(ServerBmcInfo)
    collector.host = "10.0.0.10"
    collector.port = 443

    payloads = {
        "/redfish/v1/Systems/": {"Members": [{"@odata.id": "/redfish/v1/Systems/1"}]},
        "/redfish/v1/Systems/1": {
            "Manufacturer": "Dell",
            "Model": "R750",
            "SerialNumber": "SN001",
            "PowerState": "On",
            "Status": {"Health": "OK"},
            "ProcessorSummary": {"Count": 2},
            "MemorySummary": {"TotalSystemMemoryGiB": 256},
            "BiosVersion": "1.2.3",
        },
        "/redfish/v1/Systems/1/Processors/": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Processors/CPU1"}]},
        "/redfish/v1/Systems/1/Processors/CPU1": {
            "Name": "CPU 1",
            "Model": "Xeon",
            "TotalCores": 32,
            "MaxSpeedMHz": 3200,
            "Status": {"Health": "OK"},
        },
        "/redfish/v1/Systems/1/Memory/": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Memory/DIMM1"}]},
        "/redfish/v1/Systems/1/Memory/DIMM1": {
            "Name": "DIMM1",
            "CapacityMiB": 32768,
            "OperatingSpeedMhz": 3200,
            "MemoryDeviceType": "DDR4",
            "DeviceLocator": "A1",
            "Status": {"Health": "OK"},
        },
        "/redfish/v1/Systems/1/EthernetInterfaces/": {
            "Members": [{"@odata.id": "/redfish/v1/Systems/1/EthernetInterfaces/NIC1"}]
        },
        "/redfish/v1/Systems/1/EthernetInterfaces/NIC1": {
            "Name": "NIC1",
            "MACAddress": "00:11:22:33:44:55",
            "SpeedMbps": 10000,
            "Status": {"Health": "OK"},
        },
        "/redfish/v1/Systems/1/Storage/": {"Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/RAID"}]},
        "/redfish/v1/Systems/1/Storage/RAID": {
            "Drives": [{"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Drives/0"}],
            "Volumes": {"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Volumes"},
        },
        "/redfish/v1/Systems/1/Storage/RAID/Drives/0": {
            "Name": "Disk0",
            "CapacityBytes": 1073741824,
            "Protocol": "SAS",
            "MediaType": "SSD",
            "RotationSpeedRPM": 0,
            "Status": {"Health": "OK"},
        },
        "/redfish/v1/Systems/1/Storage/RAID/Volumes": {
            "Members": [{"@odata.id": "/redfish/v1/Systems/1/Storage/RAID/Volumes/0"}]
        },
        "/redfish/v1/Systems/1/Storage/RAID/Volumes/0": {
            "Name": "VD0",
            "RAIDType": "RAID1",
            "CapacityBytes": 1073741824,
            "VolumeType": "Mirrored",
            "Status": {"Health": "OK"},
        },
    }

    monkeypatch.setattr(collector, "_safe_get", lambda _name, path: payloads.get(path, {}))

    result = collector.list_all_resources()["result"]
    assert set(result) == {
        "server_bmc",
        "server_bmc_cpu",
        "server_bmc_memory",
        "server_bmc_disk",
        "server_bmc_vdisk",
        "server_bmc_nic",
    }
    assert result["server_bmc"][0]["serial_number"] == "SN001"
    assert result["server_bmc_cpu"][0]["cores"] == 32
    assert result["server_bmc_disk"][0]["disk_media"] == "SSD"
    assert result["server_bmc_vdisk"][0]["raid_level"] == "RAID1"
    assert result["server_bmc_nic"][0]["mac_addr"] == "00:11:22:33:44:55"


def test_nacos_collector_maps_formatter_fields(monkeypatch):
    from enterprise.plugins.inputs.nacos.nacos_info import NacosInfo

    collector = object.__new__(NacosInfo)
    collector.host = "10.0.0.20"
    collector.port = 8848
    collector.access_token = ""

    payloads = {
        "state": {"version": "2.4.1", "standalone_mode": "cluster", "function_mode": "All"},
        "servers": {"servers": ["10.0.0.20:8848", {"ip": "10.0.0.21", "port": 8848, "state": "UP"}]},
        "metrics": {"serviceCount": 3, "instanceCount": 7},
        "namespaces": {
            "data": [
                {"namespace": "public", "namespaceShowName": "Public", "configCount": 2, "quota": 200, "type": "global"}
            ]
        },
        "configs": {"totalCount": 5},
        "services": {"doms": ["DEFAULT_GROUP@@svc-a"], "count": 1},
    }

    def fake_safe_get(name, _path, **_params):
        return payloads[name]

    monkeypatch.setattr(collector, "_login", lambda: None)
    monkeypatch.setattr(collector, "_safe_get", fake_safe_get)

    result = collector.list_all_resources()["result"]
    assert set(result) == {"nacos", "nacos_node", "nacos_namespace", "nacos_service"}
    assert result["nacos"][0]["node_count"] == 2
    assert result["nacos_node"][0]["ip"] == "10.0.0.20"
    assert result["nacos_node"][0]["port"] == 8848
    assert result["nacos_namespace"][0]["namespace_id"] == "public"
    assert result["nacos_service"][0]["service_name"] == "svc-a"
    assert result["nacos_service"][0]["group_name"] == "DEFAULT_GROUP"


def test_nacos_safe_get_masks_secrets_in_error_logs(monkeypatch):
    from enterprise.plugins.inputs.nacos import nacos_info
    from enterprise.plugins.inputs.nacos.nacos_info import NacosInfo

    collector = object.__new__(NacosInfo)
    collector.access_token = "SECRET"
    logged = []

    def fake_get(_path, **_params):
        raise RuntimeError("GET http://x/nacos?accessToken=SECRET&password=PWD&token=TOK failed")

    def fake_warning(message, *args):
        logged.append(message % args)

    monkeypatch.setattr(collector, "_get", fake_get)
    monkeypatch.setattr(nacos_info.logger, "warning", fake_warning)

    assert collector._safe_get("state", "/nacos") is None
    text = "\n".join(logged)
    assert "SECRET" not in text
    assert "PWD" not in text
    assert "TOK" not in text
    assert "accessToken=***" in text
    assert "password=***" in text
    assert "token=***" in text


def test_oceanbase_collector_maps_formatter_fields(monkeypatch):
    from enterprise.plugins.inputs.oceanbase.oceanbase_info import OceanBaseInfo

    collector = object.__new__(OceanBaseInfo)
    collector.host = "10.0.0.30"
    collector.port = 2881
    collector.cursor = None
    collector.connection = None

    rows = {
        "version": [{"version": "4.3.0"}],
        "cluster": [{"value": "obcluster"}],
        "zones": [{"ZONE": "zone1", "REGION": "hz", "STATUS": "ACTIVE", "IDC": "idc1"}],
        "servers": [
            {
                "SVR_IP": "10.0.0.31",
                "SVR_PORT": 2882,
                "ZONE": "zone1",
                "STATUS": "ACTIVE",
                "BUILD_VERSION": "4.3.0",
                "CPU_CAPACITY": 16,
                "MEM_CAPACITY": 34359738368,
                "START_SERVICE_TIME": "2026-01-01 00:00:00",
                "STOP_TIME": None,
            }
        ],
        "tenants": [
            {
                "TENANT_ID": 1001,
                "TENANT_NAME": "sys",
                "TENANT_TYPE": "SYS",
                "COMPATIBILITY_MODE": "MYSQL",
                "STATUS": "NORMAL",
                "PRIMARY_ZONE": "zone1",
                "LOCALITY": "FULL{1}@zone1",
            }
        ],
    }

    monkeypatch.setattr(collector, "_connect", lambda: None)
    monkeypatch.setattr(collector, "close", lambda: None)
    monkeypatch.setattr(collector, "_safe_query", lambda name, _sql: rows[name])

    result = collector.list_all_resources()["result"]
    assert set(result) == {"oceanbase", "oceanbase_zone", "oceanbase_server", "oceanbase_tenant"}
    assert result["oceanbase"][0]["inst_name"] == "10.0.0.30-oceanbase-obcluster"
    assert result["oceanbase_zone"][0]["zone_name"] == "zone1"
    assert result["oceanbase_zone"][0]["server_count"] == 1
    assert result["oceanbase_server"][0]["svr_ip"] == "10.0.0.31"
    assert result["oceanbase_tenant"][0]["tenant_name"] == "sys"
