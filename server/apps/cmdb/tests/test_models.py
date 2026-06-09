"""CMDB Django 模型方法覆盖测试。

对照 spec/prd/CMDB·资产/自动发现：采集任务凭据加解密、类型标志、字段分组/枚举库/订阅规则模型。
"""

import importlib
import hashlib
import sys
import types

import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.models.user_personal_config import UserPersonalConfig

class _EnterpriseUnavailable:
    def __init__(self, reason: str):
        self.reason = reason

    def __getattr__(self, _name):
        pytest.skip(self.reason)

    def __call__(self, *args, **kwargs):
        pytest.skip(self.reason)


try:
    from apps.cmdb.models.custom_reporting import (
        CustomReportingBatch,
        CustomReportingCleanupReview,
        CustomReportingCredential,
        CustomReportingPendingRelation,
        CustomReportingTask,
        CustomReportingTaskScope,
    )
except (ImportError, ModuleNotFoundError) as exc:
    if getattr(exc, "name", None) not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.models"}:
        raise
    _enterprise_unavailable = _EnterpriseUnavailable("enterprise custom reporting unavailable")
    CustomReportingBatch = _enterprise_unavailable
    CustomReportingCleanupReview = _enterprise_unavailable
    CustomReportingCredential = _enterprise_unavailable
    CustomReportingPendingRelation = _enterprise_unavailable
    CustomReportingTask = _enterprise_unavailable
    CustomReportingTaskScope = _enterprise_unavailable


def test_cmdb_models_load_enterprise_models_indirectly(monkeypatch):
    import apps.cmdb.models as cmdb_models

    original_import = __import__
    imported_modules = []

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        imported_modules.append(name)
        if name == "apps.cmdb.enterprise.models":
            return types.SimpleNamespace()
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    importlib.reload(cmdb_models)

    assert "apps.cmdb.enterprise.models" in imported_modules


def test_cmdb_models_import_succeeds_without_enterprise_module(monkeypatch):
    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "apps.cmdb.enterprise.models":
            raise ModuleNotFoundError("No module named 'apps.cmdb.enterprise'", name="apps.cmdb.enterprise")
        return original_import(name, globals, locals, fromlist, level)

    sys.modules.pop("apps.cmdb.models", None)
    sys.modules.pop("apps.cmdb.enterprise", None)
    sys.modules.pop("apps.cmdb.enterprise.models", None)
    monkeypatch.setattr("builtins.__import__", fake_import)

    imported_models = importlib.import_module("apps.cmdb.models")

    assert imported_models is not None
    assert "CustomReportingTask" in imported_models.__dict__


# --------------------------------------------------------------------------
# CollectModels 密码加解密（不依赖 DB）
# --------------------------------------------------------------------------


def test_encrypt_password_empty():
    assert CollectModels.encrypt_password("") == ""
    assert CollectModels.encrypt_password(None) is None


def test_encrypt_then_decrypt_roundtrip():
    enc = CollectModels.encrypt_password("secret123")
    assert enc != "secret123"
    assert CollectModels.decrypt_password(enc) == "secret123"


def test_encrypt_password_idempotent():
    enc = CollectModels.encrypt_password("secret")
    # 已加密的再次加密应保持不变
    assert CollectModels.encrypt_password(enc) == enc


def test_decrypt_password_empty():
    assert CollectModels.decrypt_password("") == ""
    assert CollectModels.decrypt_password(None) is None


def test_decrypt_password_plaintext_fallback():
    # 非加密文本解密失败 → 回退返回原文
    assert CollectModels.decrypt_password("plaintext") == "plaintext"


# --------------------------------------------------------------------------
# CollectModels 类型标志属性
# --------------------------------------------------------------------------


def test_collect_model_type_flags():
    m = CollectModels(task_type="host", driver_type="job", params={}, format_data={})
    assert m.is_host is True
    assert m.is_k8s is False
    assert m.is_job is True

    m2 = CollectModels(task_type="k8s", driver_type="other", params={"has_network_topo": True}, format_data={})
    assert m2.is_k8s is True
    assert m2.is_network_topo is True
    assert m2.is_job is False

    m3 = CollectModels(task_type="cloud", driver_type="x", params={}, format_data={})
    assert m3.is_cloud is True
    m4 = CollectModels(task_type="db", driver_type="x", params={}, format_data={})
    assert m4.is_db is True


def test_collect_model_info_property():
    m = CollectModels(
        task_type="host", driver_type="x", params={},
        format_data={"add": [1, 2], "update": [3], "delete": [], "association": [4], "__raw_data__": [5, 6, 7]},
    )
    info = m.info
    assert info["add"]["count"] == 2
    assert info["update"]["count"] == 1
    assert info["delete"]["count"] == 0
    assert info["relation"]["count"] == 1
    assert info["raw_data"]["count"] == 3


def test_collect_model_topology_contract_properties():
    m = CollectModels(
        task_type="snmp",
        driver_type="protocol",
        model_id="network",
        params={
            "has_network_topo": True,
            "topology_protocols": ["lldp", "arp"],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 0.8,
        },
        format_data={},
    )

    assert m.is_network_topo is True
    assert m.topology_protocols == ["lldp", "arp"]
    assert m.topology_fallback_strategy == "strict_neighbors_only"
    assert m.min_confidence == 0.8


def test_collect_model_topology_contract_defaults_preserve_legacy_payloads():
    m = CollectModels(
        task_type="snmp",
        driver_type="protocol",
        model_id="network",
        params={"has_network_topo": True},
        format_data={},
    )

    assert m.is_network_topo is True
    assert m.topology_protocols == ["lldp", "cdp", "fdb", "arp"]
    assert m.topology_fallback_strategy == "prefer_neighbors_then_fdb_then_arp"
    assert m.min_confidence == 0.0


def test_collect_model_topology_contract_preserves_explicit_empty_protocol_subset():
    m = CollectModels(
        task_type="snmp",
        driver_type="protocol",
        model_id="network",
        params={
            "has_network_topo": True,
            "topology_protocols": [],
            "topology_fallback_strategy": "strict_neighbors_only",
            "min_confidence": 0.3,
        },
        format_data={},
    )

    assert m.is_network_topo is True
    assert m.topology_protocols == []
    assert m.topology_fallback_strategy == "strict_neighbors_only"
    assert m.min_confidence == 0.3


# --------------------------------------------------------------------------
# 小模型 __str__ / 持久化
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_field_group_str():
    fg = FieldGroup.objects.create(model_id="host", group_name="基础", order=1)
    assert "host" in str(fg)
    assert "FieldGroup" in repr(fg)


@pytest.mark.django_db
def test_public_enum_library_str():
    lib = PublicEnumLibrary.objects.create(library_id="lib1", name="区域", team=[1], options=[{"k": "v"}])
    assert "区域" in str(lib)
    assert "lib1" in repr(lib)


@pytest.mark.django_db
def test_subscription_rule_str():
    rule = SubscriptionRule.objects.create(name="规则1", organization=1, model_id="host", filter_type="all")
    assert "规则1" in str(rule)


@pytest.mark.django_db
def test_user_personal_config_str():
    cfg = UserPersonalConfig.objects.create(username="u1", domain="domain.com", config_key="k", config_value={"a": 1})
    assert "u1@domain.com" in str(cfg)


@pytest.mark.django_db
def test_collect_model_save_encrypts_credential(monkeypatch):
    # mock 凭据字段列表，避免依赖图数据库
    monkeypatch.setattr(
        "apps.cmdb.models.collect_model.get_collect_model_passwords",
        lambda collect_model_id, driver_type: ["password"],
    )
    m = CollectModels.objects.create(
        name="t", task_type="host", driver_type="job", model_id="host",
        cycle_value_type="cron", params={}, format_data={},
        credential={"username": "admin", "password": "secret"},
    )
    m.refresh_from_db()
    # 密码已加密存储
    assert m.credential["password"] != "secret"
    # 解密可还原
    assert CollectModels.decrypt_password(m.credential["password"]) == "secret"


@pytest.mark.django_db
def test_custom_reporting_models_str():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1, 2],
        config={"group_by": ["host"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={"token": "masked"},
    )
    batch = CustomReportingBatch.objects.create(
        task=task,
        status=CustomReportingBatch.STATUS_PENDING,
    )
    pending_relation = CustomReportingPendingRelation.objects.create(
        task=task,
        source_model_id="host",
        target_model_id="biz",
        relation_payload={"field": "biz_id"},
    )
    review = CustomReportingCleanupReview.objects.create(
        batch=batch,
        status=CustomReportingCleanupReview.STATUS_PENDING,
        review_payload={"items": []},
    )

    assert "日报任务" in str(task)
    assert "默认凭据" in str(credential)
    assert str(batch.id) in str(batch)
    assert "host" in str(pending_relation)
    assert str(batch.id) in str(review)


@pytest.mark.django_db
def test_custom_reporting_credential_only_persists_token_digest_metadata():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1],
        config={"group_by": ["host"]},
    )

    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={"token": "secret-token", "description": "readonly"},
    )
    credential.refresh_from_db()

    assert credential.credential_data == {
        "token_hash": hashlib.sha256("secret-token".encode("utf-8")).hexdigest(),
        "token_masked": True,
        "description": "readonly",
    }


@pytest.mark.django_db
def test_custom_reporting_credential_issue_rotate_revoke_lifecycle():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1],
        config={"group_by": ["host"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={"description": "readonly"},
    )

    issued_token = credential.issue_token(token="issued-token")
    credential.refresh_from_db()

    assert issued_token == "issued-token"
    assert credential.is_enabled is True
    assert credential.credential_data["token_hash"] == hashlib.sha256("issued-token".encode("utf-8")).hexdigest()
    assert credential.credential_data["token_masked"] is True
    assert credential.credential_data["description"] == "readonly"
    assert "token" not in credential.credential_data

    rotated_token = credential.rotate_token(token="rotated-token")
    credential.refresh_from_db()

    assert rotated_token == "rotated-token"
    assert credential.is_enabled is True
    assert credential.credential_data["token_hash"] == hashlib.sha256("rotated-token".encode("utf-8")).hexdigest()
    assert credential.credential_data["rotated_at"]
    assert "token" not in credential.credential_data

    credential.revoke_token()
    credential.refresh_from_db()

    assert credential.is_enabled is False
    assert credential.credential_data["description"] == "readonly"
    assert credential.credential_data["token_revoked"] is True
    assert credential.credential_data["revoked_at"]
    assert "token_hash" not in credential.credential_data
    assert "token" not in credential.credential_data


@pytest.mark.django_db
def test_custom_reporting_credential_matches_only_active_non_revoked_digest():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1],
        config={"group_by": ["host"]},
    )
    credential = CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )
    credential.issue_token(token="issued-token")
    credential.refresh_from_db()

    assert credential.matches_token("issued-token") is True
    assert credential.matches_token("wrong-token") is False

    credential.revoke_token()
    credential.refresh_from_db()

    assert credential.matches_token("issued-token") is False


@pytest.mark.django_db
def test_custom_reporting_credential_unique_constraint_blocks_multiple_rows_per_task():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1],
        config={"group_by": ["host"]},
    )
    CustomReportingCredential.objects.create(
        task=task,
        name="默认凭据",
        credential_type="api_token",
        credential_data={},
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomReportingCredential.objects.create(
                task=task,
                name="第二个凭据",
                credential_type="api_token",
                credential_data={},
            )


@pytest.mark.django_db
def test_custom_reporting_task_syncs_scope_rows_on_create_and_update():
    task = CustomReportingTask.objects.create(
        name="日报任务",
        team=[1, 2],
        config={"group_by": ["host"]},
    )

    assert list(task.scopes.order_by("team_id").values_list("team_id", "name")) == [
        (1, "日报任务"),
        (2, "日报任务"),
    ]

    task.name = "周报任务"
    task.team = [2, 3]
    task.save()

    assert list(task.scopes.order_by("team_id").values_list("team_id", "name")) == [
        (2, "周报任务"),
        (3, "周报任务"),
    ]


@pytest.mark.django_db
def test_custom_reporting_task_scope_unique_constraint_blocks_same_org_name():
    CustomReportingTask.objects.create(
        name="日报任务",
        team=[1],
        config={"group_by": ["host"]},
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CustomReportingTask.objects.create(
                name="日报任务",
                team=[1],
                config={"group_by": ["host"]},
            )

    assert CustomReportingTaskScope.objects.filter(team_id=1, name="日报任务").count() == 1


def test_custom_reporting_cleanup_review_uses_batch_as_task_source():
    field_names = {field.name for field in CustomReportingCleanupReview._meta.fields}

    assert "batch" in field_names
    assert "task" not in field_names
