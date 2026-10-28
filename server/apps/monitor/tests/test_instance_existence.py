import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services.instance_existence import EXIST_LIMIT, list_existing_monitor_instances

pytestmark = pytest.mark.django_db


def _instance(*, instance_id, ip=None, cmdb_id=None, org=1, deleted=False):
    monitor_object = MonitorObject.objects.create(
        name=f"obj-{instance_id}",
        display_name="host",
        instance_id_keys=["instance_id"],
    )
    instance = MonitorInstance.objects.create(
        id=instance_id,
        name=instance_id,
        monitor_object=monitor_object,
        ip=ip,
        cmdb_id=cmdb_id,
        is_deleted=deleted,
    )
    if org is not None:
        MonitorInstanceOrganization.objects.create(monitor_instance=instance, organization=org)
    return instance


def test_exist_by_cmdb_id_and_ip():
    _instance(instance_id="('a',)", ip="10.0.1.10", cmdb_id="uuid-a", org=1)
    _instance(instance_id="('b',)", ip="10.0.1.11", cmdb_id="uuid-b", org=2)
    result = list_existing_monitor_instances(
        cmdb_ids=["uuid-a", "uuid-b", "uuid-miss"],
        ips=["10.0.1.10", "10.0.1.11", "10.0.1.12"],
        allowed_org_ids=[1],
    )
    assert result["result"] is True
    assert result["data"]["cmdb_ids"] == ["uuid-a"]
    assert result["data"]["ips"] == ["10.0.1.10"]


def test_exist_skips_deleted_and_empty_org():
    _instance(instance_id="('gone',)", ip="10.0.1.10", cmdb_id="uuid-gone", org=1, deleted=True)
    deleted = list_existing_monitor_instances(cmdb_ids=["uuid-gone"], ips=["10.0.1.10"], allowed_org_ids=[1])
    assert deleted["data"] == {"cmdb_ids": [], "ips": []}
    empty_org = list_existing_monitor_instances(cmdb_ids=["uuid-gone"], ips=["10.0.1.10"], allowed_org_ids=[])
    assert empty_org["data"] == {"cmdb_ids": [], "ips": []}


def test_exist_rejects_oversized_payload():
    result = list_existing_monitor_instances(cmdb_ids=["u"] * (EXIST_LIMIT + 1), ips=[], allowed_org_ids=[1])
    assert result["result"] is False
    assert result["message"] == "invalid"
