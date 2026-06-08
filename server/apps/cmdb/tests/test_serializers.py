"""CMDB 序列化器校验覆盖测试（采集工具/字段分组）。

对照 spec/prd/CMDB·自动发现/模型管理：采集协议凭据校验、字段分组增改批量校验。
"""

import pytest
from types import SimpleNamespace

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.serializers.collect_serializer import CollectModelLIstSerializer, CollectModelSerializer
from apps.cmdb.serializers.collect_tool import (
    CollectToolExecuteSerializer,
    IpmiCredentialSerializer,
    SnmpCredentialSerializer,
)
from apps.cmdb.serializers.field_group import (
    BatchUpdateAttrGroupSerializer,
    FieldGroupCreateSerializer,
    FieldGroupMoveSerializer,
)


# --------------------------------------------------------------------------
# SnmpCredentialSerializer
# --------------------------------------------------------------------------


def test_snmp_v2_requires_community():
    s = SnmpCredentialSerializer(data={"version": "v2"})
    assert not s.is_valid()


def test_snmp_v2_ok():
    s = SnmpCredentialSerializer(data={"version": "v2c", "community": "public"})
    assert s.is_valid(), s.errors


def test_snmp_v3_requires_fields():
    s = SnmpCredentialSerializer(data={"version": "v3", "username": "u"})
    assert not s.is_valid()


def test_snmp_v3_authpriv_full():
    s = SnmpCredentialSerializer(data={
        "version": "v3", "username": "u", "level": "authPriv",
        "integrity": "sha", "authkey": "ak", "privacy": "aes", "privkey": "pk",
    })
    assert s.is_valid(), s.errors


def test_snmp_v3_authpriv_missing_privkey():
    s = SnmpCredentialSerializer(data={
        "version": "v3", "username": "u", "level": "authPriv",
        "integrity": "sha", "authkey": "ak", "privacy": "aes",
    })
    assert not s.is_valid()


# --------------------------------------------------------------------------
# IpmiCredentialSerializer
# --------------------------------------------------------------------------


def test_ipmi_credential_ok():
    s = IpmiCredentialSerializer(data={"username": "admin", "password": "p", "privilege": "operator"})
    assert s.is_valid(), s.errors


def test_ipmi_credential_missing_password():
    s = IpmiCredentialSerializer(data={"username": "admin"})
    assert not s.is_valid()


# --------------------------------------------------------------------------
# CollectToolExecuteSerializer
# --------------------------------------------------------------------------


def _exec_data(**over):
    base = {
        "protocol": "snmp",
        "action": "test_connection",
        "access_point_id": "ap1",
        "target": "10.0.0.1",
        "port": 161,
        "credential": {"version": "v2c", "community": "public"},
    }
    base.update(over)
    return base


def test_collect_tool_execute_ok():
    s = CollectToolExecuteSerializer(data=_exec_data())
    assert s.is_valid(), s.errors


def test_collect_tool_execute_protocol_action_mismatch():
    s = CollectToolExecuteSerializer(data=_exec_data(protocol="snmp", action="ipmi_collect"))
    assert not s.is_valid()


def test_collect_tool_execute_get_oid_requires_oid():
    s = CollectToolExecuteSerializer(data=_exec_data(action="get_oid"))
    assert not s.is_valid()


def test_collect_tool_execute_get_oid_bad_format():
    s = CollectToolExecuteSerializer(data=_exec_data(action="get_oid", oid="1.3.x"))
    assert not s.is_valid()


def test_collect_tool_execute_get_oid_ok():
    s = CollectToolExecuteSerializer(data=_exec_data(action="get_oid", oid="1.3.6.1"))
    assert s.is_valid(), s.errors


def test_collect_tool_execute_ipmi():
    s = CollectToolExecuteSerializer(data=_exec_data(
        protocol="ipmi", action="ipmi_collect",
        credential={"username": "admin", "password": "p"},
    ))
    assert s.is_valid(), s.errors


def test_collect_tool_execute_invalid_credential():
    s = CollectToolExecuteSerializer(data=_exec_data(credential={"version": "v3"}))
    assert not s.is_valid()


def test_collect_tool_execute_bad_ip():
    s = CollectToolExecuteSerializer(data=_exec_data(target="not-an-ip"))
    assert not s.is_valid()


# --------------------------------------------------------------------------
# FieldGroup serializers
# --------------------------------------------------------------------------


def test_field_group_create_ok():
    s = FieldGroupCreateSerializer(data={"group_name": "基础信息"})
    assert s.is_valid(), s.errors


def test_field_group_create_blank_name():
    s = FieldGroupCreateSerializer(data={"group_name": ""})
    assert not s.is_valid()


def test_field_group_move_ok():
    assert FieldGroupMoveSerializer(data={"direction": "up"}).is_valid()


def test_field_group_move_invalid():
    assert not FieldGroupMoveSerializer(data={"direction": "sideways"}).is_valid()


def test_batch_update_ok():
    s = BatchUpdateAttrGroupSerializer(data={"updates": [{"attr_id": "a", "group_name": "g"}]})
    assert s.is_valid(), s.errors


def test_batch_update_missing_attr_id():
    s = BatchUpdateAttrGroupSerializer(data={"updates": [{"group_name": "g"}]})
    assert not s.is_valid()


def test_batch_update_empty():
    s = BatchUpdateAttrGroupSerializer(data={"updates": []})
    assert not s.is_valid()


def _collect_model_data(**overrides):
    payload = {
        "name": "network-topology-task",
        "task_type": "snmp",
        "driver_type": "protocol",
        "model_id": "network",
        "cycle_value_type": "cron",
        "params": {
            "has_network_topo": True,
            "topology_protocols": ["lldp", "fdb"],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 0.75,
        },
        "instances": [{"ip_addr": "10.0.0.1"}],
        "credential": [{"version": "v2c", "community": "public", "snmp_port": 161}],
        "access_point": [{"id": 1}],
        "format_data": {},
        "collect_data": {},
        "collect_digest": {},
        "team": [],
    }
    payload.update(overrides)
    return payload


def _serializer_context():
    return {
        "request": SimpleNamespace(
            user=SimpleNamespace(group_list=[]),
            COOKIES={},
        )
    }


@pytest.mark.django_db
def test_collect_model_serializer_accepts_valid_network_topology_contract(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(data=_collect_model_data(), context=_serializer_context())

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["topology_protocols"] == ["lldp", "fdb"]
    assert serializer.validated_data["params"]["topology_fallback_strategy"] == "strict_neighbors_only"
    assert serializer.validated_data["params"]["min_confidence"] == 0.75


@pytest.mark.django_db
def test_collect_model_serializer_accepts_empty_topology_protocols_subset(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(
        data=_collect_model_data(
            params={
                "has_network_topo": True,
                "topology_protocols": [],
                "topology_fallback_strategy": "strict_neighbors_only",
                "min_confidence": 0.75,
            }
        ),
        context=_serializer_context(),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"]["topology_protocols"] == []


@pytest.mark.django_db
def test_collect_model_serializer_partial_update_preserves_existing_topology_contract(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(
        instance=CollectModels(
            id=102,
            name="existing-network-topology-task",
            task_type="snmp",
            driver_type="protocol",
            model_id="network",
            cycle_value_type="cron",
            params={
                "has_network_topo": True,
                "topology_protocols": ["lldp", "arp"],
                "topology_fallback_strategy": "strict_neighbors_only",
                "min_confidence": 0.6,
            },
            instances=[{"ip_addr": "10.0.0.1"}],
            credential=[{"version": "v2c", "community": "public", "snmp_port": 161}],
            access_point=[{"id": 1}],
            format_data={},
            collect_data={},
            collect_digest={},
            team=[],
        ),
        data={"params": {"has_network_topo": True}},
        partial=True,
        context=_serializer_context(),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"] == {
        "has_network_topo": True,
        "topology_protocols": ["lldp", "arp"],
        "topology_fallback_strategy": "strict_neighbors_only",
        "min_confidence": 0.6,
    }


@pytest.mark.django_db
def test_collect_model_serializer_partial_disable_preserves_existing_topology_contract(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(
        instance=CollectModels(
            id=103,
            name="existing-network-topology-task",
            task_type="snmp",
            driver_type="protocol",
            model_id="network",
            cycle_value_type="cron",
            params={
                "has_network_topo": True,
                "topology_protocols": ["fdb"],
                "topology_fallback_strategy": "strict_neighbors_only",
                "min_confidence": 0.35,
            },
            instances=[{"ip_addr": "10.0.0.1"}],
            credential=[{"version": "v2c", "community": "public", "snmp_port": 161}],
            access_point=[{"id": 1}],
            format_data={},
            collect_data={},
            collect_digest={},
            team=[],
        ),
        data={"params": {"has_network_topo": False}},
        partial=True,
        context=_serializer_context(),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"] == {
        "has_network_topo": False,
        "topology_protocols": ["fdb"],
        "topology_fallback_strategy": "strict_neighbors_only",
        "min_confidence": 0.35,
    }


@pytest.mark.django_db
def test_collect_model_serializer_representation_normalizes_legacy_topology_contract(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(
        instance=SimpleNamespace(
            id=101,
            name="legacy-network-topology-task",
            task_type="snmp",
            driver_type="protocol",
            model_id="network",
            cycle_value_type="cron",
            params={"has_network_topo": True},
            instances=[{"ip_addr": "10.0.0.1"}],
            credential=[{"version": "v2c", "community": "public", "snmp_port": 161}],
            access_point=[{"id": 1}],
            format_data={},
            collect_data={},
            collect_digest={},
            team=[],
        ),
        context=_serializer_context(),
    )

    assert serializer.data["params"] == {
        "has_network_topo": True,
        "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
        "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
        "min_confidence": 0.0,
    }


@pytest.mark.django_db
def test_collect_model_list_serializer_representation_normalizes_legacy_topology_contract(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelLIstSerializer(
        instance=SimpleNamespace(
            id=104,
            name="legacy-network-topology-task",
            task_type="snmp",
            driver_type="protocol",
            model_id="network",
            exec_status="pending",
            updated_at=None,
            collect_digest={},
            exec_time=None,
            created_by="tester",
            input_method="manual",
            params={"has_network_topo": True},
            team=[],
            data_cleanup_strategy="overwrite",
            expire_days=30,
        ),
        context=_serializer_context(),
    )

    assert serializer.data["params"] == {
        "has_network_topo": True,
        "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
        "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
        "min_confidence": 0.0,
    }


@pytest.mark.django_db
def test_collect_model_serializer_allows_stale_topology_fields_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(
        data=_collect_model_data(
            params={
                "has_network_topo": False,
                "topology_protocols": "bogus",
                "topology_fallback_strategy": "best_effort",
                "min_confidence": 2,
            }
        ),
        context=_serializer_context(),
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["params"] == {
        "has_network_topo": False,
        "topology_protocols": ["lldp", "cdp", "fdb", "arp"],
        "topology_fallback_strategy": "prefer_neighbors_then_fdb_then_arp",
        "min_confidence": 0.0,
    }


@pytest.mark.parametrize(
    "params",
    [
        {
            "has_network_topo": True,
            "topology_protocols": ["lldp", "bogus"],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 0.75,
        },
        {
            "has_network_topo": True,
            "topology_protocols": ["lldp"],
            "topology_fallback_strategy": "best_effort",
            "min_confidence": 0.75,
        },
        {
            "has_network_topo": True,
            "topology_protocols": ["lldp"],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 1.2,
        },
    ],
)
@pytest.mark.django_db
def test_collect_model_serializer_rejects_invalid_network_topology_contract(monkeypatch, params):
    monkeypatch.setattr(
        "apps.core.utils.serializers.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children: {},
    )
    serializer = CollectModelSerializer(data=_collect_model_data(params=params), context=_serializer_context())

    assert not serializer.is_valid()
