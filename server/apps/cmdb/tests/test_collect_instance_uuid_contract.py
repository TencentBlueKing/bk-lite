from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

HOST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"
SUBNET_UUID = "73e4a531-b6bb-43cc-9eae-8eb8a09f795e"


@pytest.fixture(autouse=True)
def _stub_auth_serializer_dependencies(monkeypatch):
    class _UserQuery:
        @staticmethod
        def values(*args):
            return []

    class _UserManager:
        @staticmethod
        def all():
            return _UserQuery()

    monkeypatch.setattr("apps.core.utils.serializers.User.objects", _UserManager())
    monkeypatch.setattr("apps.core.utils.serializers.get_permission_rules", lambda *args, **kwargs: {})
    monkeypatch.setattr(CollectModelSerializer.Meta, "validators", [], raising=False)
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {
                "inst_uuid": inst_uuid,
                "model_id": "subnet" if inst_uuid == SUBNET_UUID else "host",
                "inst_name": "trusted-host",
                "ip_addr": "10.0.0.8",
            }
            for inst_uuid in uuids
        ],
    )


def _serializer(*, model_id="host", instances, timeout=60):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(
        data={
            "name": f"{model_id}-uuid-contract",
            "task_type": CollectPluginTypes.IP if model_id == "ip" else CollectPluginTypes.HOST,
            "driver_type": CollectDriverTypes.PROTOCOL,
            "model_id": model_id,
            "cycle_value_type": "cycle",
            "instances": instances,
            "access_point": [{"id": 1}],
            "credential": [],
            "timeout": timeout,
            "params": {},
            "team": [1],
        },
        context={"request": request},
    )


def _legacy_ip_update_serializer(*, existing_timeout, submitted_timeout):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    instance = CollectModels(
        name="legacy-ip-task",
        task_type=CollectPluginTypes.IP,
        driver_type=CollectDriverTypes.PROTOCOL,
        model_id="ip",
        timeout=existing_timeout,
    )
    return CollectModelSerializer(
        instance,
        data={"timeout": submitted_timeout},
        partial=True,
        context={"request": request},
    )


def test_collect_task_builds_trusted_snapshot_from_uuid():
    serializer = _serializer(
        instances=[
            {
                "inst_uuid": HOST_UUID,
                "model_id": "host",
                "inst_name": "forged-name",
                "ip_addr": "203.0.113.7",
                "credential": {"password": "forged"},
            }
        ]
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["instances"] == [
        {
            "inst_uuid": HOST_UUID,
            "model_id": "host",
            "inst_name": "trusted-host",
            "ip_addr": "10.0.0.8",
        }
    ]


def test_collect_task_rejects_numeric_instance_identity():
    serializer = _serializer(instances=[{"_id": 7, "model_id": "host", "inst_name": "host-a"}])

    assert serializer.is_valid() is False
    assert "inst_uuid" in str(serializer.errors)


def test_collect_task_rejects_graph_id_even_when_uuid_is_present():
    serializer = _serializer(instances=[{"_id": 7, "inst_uuid": HOST_UUID, "model_id": "host"}])

    assert serializer.is_valid() is False
    assert "_id/inst_id" in str(serializer.errors)


def test_collect_task_rejects_uuid_without_instance_permission(monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission",
        lambda *args, **kwargs: False,
    )
    serializer = _serializer(instances=[{"inst_uuid": HOST_UUID}])

    assert serializer.is_valid() is False
    assert "访问权限" in str(serializer.errors)


def test_ip_task_accepts_subnet_uuids():
    serializer = _serializer(
        model_id="ip",
        instances={
            "subnet_uuids": [SUBNET_UUID],
            "scan_method": "icmp",
        },
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["instances"] == {
        "subnet_uuids": [SUBNET_UUID],
        "scan_method": "icmp",
    }


def test_ip_task_rejects_new_scan_budget_below_30_seconds():
    serializer = _serializer(
        model_id="ip",
        instances={"subnet_uuids": [SUBNET_UUID], "scan_method": "icmp"},
        timeout=29,
    )

    assert serializer.is_valid() is False
    assert serializer.errors["timeout"] == ["IP 采集任务超时时间不能小于 30 秒"]


def test_ip_task_accepts_30_second_scan_budget():
    serializer = _serializer(
        model_id="ip",
        instances={"subnet_uuids": [SUBNET_UUID], "scan_method": "icmp"},
        timeout=30,
    )

    assert serializer.is_valid(), serializer.errors


def test_ip_task_preserves_unchanged_legacy_scan_budget_on_edit():
    serializer = _legacy_ip_update_serializer(existing_timeout=5, submitted_timeout=5)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["timeout"] == 5


def test_ip_task_rejects_changing_legacy_scan_budget_to_another_low_value():
    serializer = _legacy_ip_update_serializer(existing_timeout=5, submitted_timeout=10)

    assert serializer.is_valid() is False
    assert serializer.errors["timeout"] == ["IP 采集任务超时时间不能小于 30 秒"]


def test_ip_task_rejects_digit_only_subnet_write():
    serializer = _serializer(
        model_id="ip",
        instances={"subnet_ids": [7], "scan_method": "icmp"},
    )

    assert serializer.is_valid() is False
    assert "subnet_uuids" in str(serializer.errors)
