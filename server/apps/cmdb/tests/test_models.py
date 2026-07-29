"""CMDB Django 模型方法覆盖测试。

对照 specs/capabilities/legacy-prd-cmdb-资产.md/自动发现：采集任务凭据加解密、类型标志、字段分组/枚举库/订阅规则模型。
"""

import pytest

from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.models.public_enum_library import PublicEnumLibrary
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.models.user_personal_config import UserPersonalConfig


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
