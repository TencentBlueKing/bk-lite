import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService

pytestmark = pytest.mark.unit


def test_existing_hosts_are_indexed_by_ip_and_cloud_and_invalid_rows_are_ignored(mocker):
    search_inst = mocker.patch.object(
        InstanceManage,
        "search_inst",
        return_value=(
            [
                {"_id": "host-1", "ip_addr": " 10.0.0.1 ", "cloud": 7},
                {"_id": "host-2", "ip_addr": "10.0.0.2", "cloud_id": "8"},
                {"_id": "missing-ip", "cloud": 7},
                {"_id": "missing-cloud", "ip_addr": "10.0.0.3"},
            ],
            4,
        ),
    )

    indexed = NodeMgmtSyncService._load_existing_host_map(task_id=99)

    search_inst.assert_called_once_with(model_id="host")
    assert indexed == {
        ("10.0.0.1", 7): {"_id": "host-1", "ip_addr": " 10.0.0.1 ", "cloud": 7},
        ("10.0.0.2", 8): {"_id": "host-2", "ip_addr": "10.0.0.2", "cloud_id": "8"},
    }


def test_existing_host_scan_fails_closed_when_host_budget_is_exceeded(mocker):
    mocker.patch.object(NodeMgmtSyncService, "MAX_EXISTING_HOSTS", 1, create=True)
    mocker.patch.object(
        InstanceManage,
        "search_inst",
        return_value=([{"_id": 1}, {"_id": 2}], 2),
    )

    with pytest.raises(RuntimeError, match="HOST_SCAN_LIMIT_EXCEEDED"):
        NodeMgmtSyncService._load_existing_host_map(task_id=0)


def test_existing_host_scan_fails_closed_when_byte_budget_is_exceeded(mocker, caplog):
    mocker.patch.object(NodeMgmtSyncService, "MAX_EXISTING_HOST_BYTES", 8, create=True)
    mocker.patch.object(
        InstanceManage,
        "search_inst",
        return_value=([{"_id": 1, "secret": "raw-sensitive-value"}], 1),
    )

    with pytest.raises(RuntimeError, match="HOST_SCAN_BYTES_EXCEEDED"):
        NodeMgmtSyncService._load_existing_host_map(task_id=0)

    assert "raw-sensitive-value" not in caplog.text


def test_region_collection_reuses_only_hosts_matching_both_ip_and_cloud(mocker):
    existing = {
        ("10.0.0.1", 7): {"_id": "region-7-host"},
        ("10.0.0.1", 8): {"_id": "region-8-host"},
    }
    mocker.patch.object(NodeMgmtSyncService, "_load_existing_host_map", return_value=existing)

    instances = NodeMgmtSyncService._query_region_host_instances(7, [{"ip": "10.0.0.1"}, {"ip_addr": "10.0.0.2"}, {"ip": ""},],)

    assert instances == [{"_id": "region-7-host"}]


def test_host_payload_normalizes_runtime_enum_keywords_and_persistence_fields(mocker):
    mocker.patch.object(
        ModelManage,
        "search_model_info",
        return_value={
            "attrs": [
                {"attr_id": "os_type", "option": [{"id": "custom-linux", "name": "Custom Linux"}, {"id": "win-server", "name": "Windows Server"}]}
            ]
        },
    )
    mocker.patch.object(
        ModelManage,
        "resolve_runtime_enum_options",
        return_value=[{"id": "custom-linux", "name": "Custom Linux"}, {"id": "win-server", "name": "Windows Server"}, "invalid-option",],
    )

    custom = NodeMgmtSyncService._build_host_instance_payload(
        node={
            "id": "node-7",
            "ip": " 10.0.0.7 ",
            "cloud_region_id": "7",
            "cloud_region_name": "华东",
            "organization_ids": [3, "1", "bad", 1],
            "operating_system": "custom linux",
            "password": "must-not-persist",
        },
        collect_task_id=88,
    )

    assert custom["inst_name"] == "10.0.0.7[华东]"
    assert custom["ip_addr"] == "10.0.0.7"
    assert custom["organization"] == [1, 3]
    assert custom["cloud"] == 7
    assert custom["os_type"] == "custom-linux"
    assert custom["collect_task"] == 88
    assert "password" not in custom

    assert NodeMgmtSyncService._map_host_os_type("Ubuntu 24.04") == "1"
    assert NodeMgmtSyncService._map_host_os_type("win11") == "2"
    assert NodeMgmtSyncService._map_host_os_type("AIX") == "3"
    assert NodeMgmtSyncService._map_host_os_type("Unix") == "4"
    assert NodeMgmtSyncService._map_host_os_type("Plan 9") == "other"
    assert NodeMgmtSyncService._map_host_os_type("") == "other"
