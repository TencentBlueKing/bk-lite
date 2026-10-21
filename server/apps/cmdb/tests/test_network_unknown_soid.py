"""网络发现未识别 SOID 的补映射与写入。"""

from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels, OidMapping
from apps.cmdb.services.network_unknown_soid import save_unknown_soid_mappings, write_unknown_devices
from apps.core.exceptions.base_app_exception import ForbiddenException, ValidationAppException

pytestmark = pytest.mark.django_db

SOID_A = "1.3.6.1.4.1.99999.1"
SOID_B = "1.3.6.1.4.1.99999.2"
OPERATOR = SimpleNamespace(is_superuser=True, permission={})
NO_SOID_ADD = SimpleNamespace(is_superuser=False, permission={"cmdb": {"auto_collection-Execute"}})


def _groups():
    return [
        {
            "soid": SOID_A,
            "devices": [
                {
                    "ip_addr": "10.0.0.8",
                    "port": "161",
                    "sys_desc": "box-a",
                    "interfaces": [{"name": "Gi0", "description": "uplink", "mac": "aa", "status": "UP"}],
                },
                {"ip_addr": "10.0.0.9", "port": "161", "sys_desc": "box-b", "interfaces": []},
            ],
        },
        {
            "soid": SOID_B,
            "devices": [{"ip_addr": "10.0.0.10", "port": "161", "sys_desc": "box-c", "interfaces": []}],
        },
    ]


def _task(**overrides):
    payload = {
        "name": overrides.pop("name", "net-unknown"),
        "task_type": "snmp",
        "driver_type": "protocol",
        "model_id": "network",
        "cycle_value_type": "cycle",
        "team": [1],
        "exec_status": CollectRunStatusType.SUCCESS,
        "format_data": {"add": [], "unresolved": _groups()},
        "topology_snapshot": {"links": [{"id": "keep"}]},
    }
    payload.update(overrides)
    return CollectModels.objects.create(**payload)


def test_save_mappings_dedupes_soid_and_leaves_devices_unresolved():
    task = _task()

    result = save_unknown_soid_mappings(
        task,
        OPERATOR,
        [
            {"soid": SOID_A, "device_type": "firewall", "brand": "Hillstone", "model": "SG-6000"},
            {"soid": "." + SOID_A, "device_type": "router", "brand": "Other", "model": "Other"},
        ],
    )

    assert len(result["created"]) == 1
    assert result["skipped"] == []
    row = OidMapping.objects.get(oid=SOID_A)
    assert row.built_in is False
    assert row.device_type == "firewall"
    assert row.brand == "Hillstone"
    task.refresh_from_db()
    assert task.format_data["unresolved"][0]["devices"][0]["ip_addr"] == "10.0.0.8"


def test_existing_mapping_is_skipped_and_not_modified():
    OidMapping.objects.create(oid=SOID_A, model="旧型号", brand="旧品牌", device_type="router", built_in=True)
    task = _task()

    result = save_unknown_soid_mappings(
        task,
        OPERATOR,
        [{"soid": SOID_A, "device_type": "firewall", "brand": "Hillstone", "model": "SG-6000"}],
    )

    assert result["created"] == []
    assert result["skipped"] == [{"soid": SOID_A, "device_type": "router", "brand": "旧品牌", "model": "旧型号"}]
    row = OidMapping.objects.get(oid=SOID_A)
    assert row.model == "旧型号"
    assert row.device_type == "router"
    assert OidMapping.objects.count() == 1


def test_write_uses_library_brand_and_drops_only_requested_ips():
    OidMapping.objects.create(oid=SOID_A, model="SG-6000", brand="Hillstone", device_type="firewall", built_in=False)
    task = _task()
    seen = {}

    def ingest(current, rows_by_model):
        seen["task_id"] = current.id
        seen["rows"] = rows_by_model
        return {}

    result = write_unknown_devices(task, OPERATOR, ["10.0.0.8"], ingest=ingest)

    assert result == {"written": ["10.0.0.8"]}
    assert list(seen["rows"]) == ["firewall", "interface"]
    device = seen["rows"]["firewall"][0]
    assert device["brand"] == "Hillstone"
    assert device["model"] == "SG-6000"
    assert device["inst_name"] == "10.0.0.8-firewall"
    assert device["sys_desc"] == "box-a"
    assert "未知" not in (device["brand"], device["model"])
    interface = seen["rows"]["interface"][0]
    assert interface["inst_name"] == "10.0.0.8-firewall-Gi0"
    assert interface["assos"][0]["model_asst_id"] == "interface_belong_firewall"
    task.refresh_from_db()
    groups = {group["soid"]: group for group in task.format_data["unresolved"]}
    assert [item["ip_addr"] for item in groups[SOID_A]["devices"]] == ["10.0.0.9"]
    assert groups[SOID_B]["devices"][0]["ip_addr"] == "10.0.0.10"
    assert task.topology_snapshot == {"links": [{"id": "keep"}]}


def test_write_rejects_whole_batch_when_any_soid_has_no_mapping():
    OidMapping.objects.create(oid=SOID_A, model="SG-6000", brand="Hillstone", device_type="firewall", built_in=False)
    task = _task()
    called = []

    with pytest.raises(ValidationAppException) as exc:
        write_unknown_devices(task, OPERATOR, ["10.0.0.8", "10.0.0.10"], ingest=lambda *args: called.append(args))

    assert exc.value.data["missing_soids"] == [SOID_B]
    assert called == []
    task.refresh_from_db()
    assert len(task.format_data["unresolved"]) == 2


def test_write_failure_keeps_mapping_and_unresolved_devices():
    task = _task()
    save_unknown_soid_mappings(
        task,
        OPERATOR,
        [{"soid": SOID_A, "device_type": "switch", "brand": "Cisco", "model": "C9300"}],
    )

    def boom(current, rows_by_model):
        raise RuntimeError("graph down")

    with pytest.raises(RuntimeError, match="graph down"):
        write_unknown_devices(task, OPERATOR, ["10.0.0.8"], ingest=boom)

    assert OidMapping.objects.filter(oid=SOID_A, brand="Cisco").exists()
    task.refresh_from_db()
    assert task.format_data["unresolved"][0]["devices"][0]["ip_addr"] == "10.0.0.8"


@pytest.mark.parametrize("exec_status", [CollectRunStatusType.NOT_START, CollectRunStatusType.RUNNING, CollectRunStatusType.WRITING])
def test_non_terminal_task_is_rejected(exec_status):
    task = _task(exec_status=exec_status)
    with pytest.raises(ValidationAppException):
        save_unknown_soid_mappings(task, OPERATOR, [{"soid": SOID_A, "device_type": "switch", "brand": "Cisco", "model": "C9300"}])


def test_non_network_empty_brand_bad_type_and_missing_permission_are_rejected():
    network = _task()
    host = _task(name="host-task", model_id="host", task_type="host")
    with pytest.raises(ValidationAppException):
        save_unknown_soid_mappings(host, OPERATOR, [{"soid": SOID_A, "device_type": "switch", "brand": "Cisco", "model": "C9300"}])
    with pytest.raises(ValidationAppException):
        save_unknown_soid_mappings(network, OPERATOR, [{"soid": SOID_A, "device_type": "switch", "brand": "  ", "model": "C9300"}])
    with pytest.raises(ValidationAppException):
        save_unknown_soid_mappings(network, OPERATOR, [{"soid": SOID_A, "device_type": "security_device", "brand": "Cisco", "model": "C9300"}])
    with pytest.raises(ForbiddenException):
        save_unknown_soid_mappings(network, NO_SOID_ADD, [{"soid": SOID_A, "device_type": "switch", "brand": "Cisco", "model": "C9300"}])
    assert OidMapping.objects.count() == 0
