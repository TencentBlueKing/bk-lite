from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.serializers.collect_serializer import CollectModelSerializer

_SSL_CER_INST_UUID = "63e4a531-b6bb-43cc-9eae-8eb8a09f795e"


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
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        CollectModelSerializer.Meta,
        "validators",
        [],
        raising=False,
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage.query_entity_by_uuids",
        lambda uuids: [
            {
                "inst_uuid": inst_uuid,
                "model_id": "ssl_cer",
                "inst_name": "rex-test",
                "domain": "www.baidu.cn",
            }
            for inst_uuid in uuids
        ],
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apps.cmdb.serializers.collect_serializer.InstanceManage._has_topology_view_permission",
        lambda *args, **kwargs: True,
    )


def _payload(*, instances, ip_range=""):
    return {
        "name": "ssl-cer-collect",
        "task_type": CollectPluginTypes.PROTOCOL,
        "driver_type": CollectDriverTypes.PROTOCOL,
        "model_id": "ssl_cer",
        "access_point": [{"id": 1}],
        "instances": instances,
        "ip_range": ip_range,
        "cycle_value_type": "cycle",
        "cycle_value": "5",
        "scan_cycle": "5",
        "timeout": 600,
        "team": [1],
        "params": {},
        "credential": [],
    }


def _serializer(*, instances, ip_range=""):
    request = SimpleNamespace(user=SimpleNamespace(group_list=[]), COOKIES={})
    return CollectModelSerializer(
        data=_payload(instances=instances, ip_range=ip_range),
        context={"request": request},
    )


def _ssl_cer_instance():
    return {
        "inst_uuid": _SSL_CER_INST_UUID,
        "model_id": "ssl_cer",
        "inst_name": "rex-test",
        "domain": "www.baidu.cn",
    }


def test_ssl_cer_serializer_rejects_ip_range():
    serializer = _serializer(instances=[_ssl_cer_instance()], ip_range="10.0.0.1-10.0.0.2")

    assert serializer.is_valid() is False
    assert "ip_range" in serializer.errors


def test_ssl_cer_serializer_rejects_empty_instances():
    serializer = _serializer(instances=[])

    assert serializer.is_valid() is False
    assert "instances" in serializer.errors


def test_ssl_cer_serializer_accepts_named_instances_and_clears_ip_range():
    serializer = _serializer(instances=[_ssl_cer_instance()])

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["ip_range"] == ""
    assert serializer.validated_data["credential"] == []
    assert serializer.validated_data["driver_type"] == CollectDriverTypes.PROTOCOL
    assert serializer.validated_data["instances"][0]["inst_name"] == "rex-test"
    assert serializer.validated_data["instances"][0]["domain"] == "www.baidu.cn"
