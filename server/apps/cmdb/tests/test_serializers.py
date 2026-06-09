"""CMDB 序列化器校验覆盖测试（采集工具/字段分组）。

对照 spec/prd/CMDB·自动发现/模型管理：采集协议凭据校验、字段分组增改批量校验。
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
from apps.cmdb.services.model import ModelManage
from apps.system_mgmt.models import Group


class _EnterpriseUnavailable:
    def __init__(self, reason: str):
        self.reason = reason

    def __getattr__(self, _name):
        pytest.skip(self.reason)

    def __call__(self, *args, **kwargs):
        pytest.skip(self.reason)


try:
    from apps.cmdb.serializers.custom_reporting import (
        CustomReportingIngestSerializer,
        CustomReportingTaskSerializer,
    )
    from apps.cmdb.models.custom_reporting import CustomReportingTask
except (ImportError, ModuleNotFoundError) as exc:
    if getattr(exc, "name", None) not in {
        "apps.cmdb.enterprise",
        "apps.cmdb.enterprise.serializers",
        "apps.cmdb.enterprise.models",
    }:
        raise
    _enterprise_unavailable = _EnterpriseUnavailable("enterprise custom reporting unavailable")
    CustomReportingIngestSerializer = _enterprise_unavailable
    CustomReportingTaskSerializer = _enterprise_unavailable
    CustomReportingTask = _enterprise_unavailable


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


@pytest.mark.django_db
def test_custom_reporting_task_serializer_rejects_overlapping_team_duplicate_name():
    group_one = Group.objects.create(name="组织一")
    group_two = Group.objects.create(name="组织二")
    group_three = Group.objects.create(name="组织三")
    CustomReportingTask.objects.create(
        name="资产日报",
        team=[group_one.id, group_two.id],
        config={"metrics": ["count"]},
    )

    serializer = CustomReportingTaskSerializer(
        data={
            "name": "资产日报",
            "team": [group_two.id, group_three.id],
            "config": {"metrics": ["count"]},
        }
    )

    assert not serializer.is_valid()
    assert "name" in serializer.errors


@pytest.mark.django_db
def test_custom_reporting_task_serializer_allows_non_overlapping_team_duplicate_name():
    group_one = Group.objects.create(name="组织一")
    group_two = Group.objects.create(name="组织二")
    group_three = Group.objects.create(name="组织三")
    CustomReportingTask.objects.create(
        name="资产日报",
        team=[group_one.id, group_two.id],
        config={"metrics": ["count"]},
    )

    serializer = CustomReportingTaskSerializer(
        data={"name": "资产日报", "team": [group_three.id], "config": {"metrics": ["count"]}}
    )

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_custom_reporting_task_serializer_rejects_boolean_team_id():
    serializer = CustomReportingTaskSerializer(
        data={"name": "资产日报", "team": [True], "config": {"metrics": ["count"]}}
    )

    assert not serializer.is_valid()
    assert serializer.errors["team"] == ["team 中的组织ID必须为整数"]


@pytest.mark.django_db
def test_custom_reporting_task_serializer_rejects_unknown_team_id():
    group = Group.objects.create(name="默认组织")

    serializer = CustomReportingTaskSerializer(
        data={"name": "资产日报", "team": [group.id, 999999], "config": {"metrics": ["count"]}}
    )

    assert not serializer.is_valid()
    assert serializer.errors["team"] == ["team 中存在无效的组织ID"]


@pytest.mark.django_db
def test_custom_reporting_task_serializer_rejects_quick_model_for_non_quick_mode():
    group = Group.objects.create(name="默认组织")

    serializer = CustomReportingTaskSerializer(
        data={
            "name": "普通上报",
            "team": [group.id],
            "config": {"mode": "manual", "model_id": "report_asset"},
            "quick_model": {"model_id": "quick_asset"},
        }
    )

    assert not serializer.is_valid()
    assert serializer.errors["quick_model"] == ["非 quick 模式任务不允许传 quick_model 配置"]


@pytest.mark.django_db
def test_custom_reporting_task_serializer_requires_existing_model_for_standard_mode_create(monkeypatch):
    group = Group.objects.create(name="默认组织")
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": "report_asset"} if model_id == "report_asset" else {},
        raising=False,
    )

    empty_model_serializer = CustomReportingTaskSerializer(
        data={
            "name": "普通上报",
            "team": [group.id],
            "config": {"mode": "manual", "model_id": ""},
        }
    )
    missing_model_serializer = CustomReportingTaskSerializer(
        data={
            "name": "普通上报二",
            "team": [group.id],
            "config": {"mode": "manual", "model_id": "missing_model"},
        }
    )

    assert not empty_model_serializer.is_valid()
    assert empty_model_serializer.errors["config"] == ["标准模式任务需要有效的 config.model_id 配置"]
    assert not missing_model_serializer.is_valid()
    assert missing_model_serializer.errors["config"] == ["标准模式任务绑定的模型不存在"]


@pytest.mark.django_db
def test_custom_reporting_task_serializer_rejects_clearing_standard_mode_model_on_update(monkeypatch):
    group = Group.objects.create(name="默认组织")
    task = CustomReportingTask.objects.create(
        name="普通上报",
        team=[group.id],
        config={"mode": "manual", "model_id": "report_asset"},
    )
    monkeypatch.setattr(
        ModelManage,
        "search_model_info",
        lambda model_id: {"model_id": "report_asset"} if model_id == "report_asset" else {},
        raising=False,
    )

    serializer = CustomReportingTaskSerializer(
        instance=task,
        data={"name": "普通上报", "team": [group.id], "config": {}},
    )

    assert not serializer.is_valid()
    assert serializer.errors["config"] == ["标准模式任务需要有效的 config.model_id 配置"]


def test_custom_reporting_ingest_serializer_rejects_relation_without_source_and_target():
    serializer = CustomReportingIngestSerializer(
        data={
            "instances": [{"identity": {"asset_code": "asset-1"}}],
            "relations": [{"relation_type": "depends_on"}],
            "batch_metadata": {"source": "agent"},
        }
    )

    assert not serializer.is_valid()
    assert "source" in serializer.errors["relations"][0]
    assert "target" in serializer.errors["relations"][0]


def test_custom_reporting_ingest_serializer_rejects_relation_source_without_identity():
    serializer = CustomReportingIngestSerializer(
        data={
            "instances": [],
            "relations": [
                {
                    "source": {"model_id": "host"},
                    "target": {"inst_name": "db-01"},
                    "relation_type": "depends_on",
                }
            ],
            "batch_metadata": {},
        }
    )

    assert not serializer.is_valid()
    assert serializer.errors["relations"][0]["source"] == ["source 缺少 identity key"]


def test_custom_reporting_ingest_serializer_rejects_relation_with_empty_source_and_target():
    serializer = CustomReportingIngestSerializer(
        data={
            "instances": [{"identity": {"asset_code": "asset-1"}}],
            "relations": [
                {
                    "source": {},
                    "target": {},
                    "relation_type": "depends_on",
                }
            ],
            "batch_metadata": {"source": "agent"},
        }
    )

    assert not serializer.is_valid()
    assert serializer.errors["relations"][0]["source"] == ["source 不能为空对象"]
    assert serializer.errors["relations"][0]["target"] == ["target 不能为空对象"]
