"""CMDB 序列化器校验覆盖测试（采集工具/字段分组）。

对照 specs/capabilities/legacy-prd-cmdb-自动发现.md：采集协议凭据校验、字段分组增改批量校验。
"""

import pytest

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
