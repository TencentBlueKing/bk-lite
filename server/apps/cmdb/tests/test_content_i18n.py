"""CMDB 内置属性/分组展示名覆盖（不依赖 Django migrate）。"""

import pytest

from apps.cmdb.language.service import (
    SettingLanguage,
    apply_attr_translations,
    catalog_display_name,
    group_display_name,
    mark_catalog_name_customized,
    model_object_display_name,
    normalize_cmdb_language,
)

pytestmark = pytest.mark.unit


def test_normalize_cmdb_language():
    assert normalize_cmdb_language("en-US") == "en"
    assert normalize_cmdb_language("zh-CN") == "zh-Hans"
    assert normalize_cmdb_language(None) == "zh-Hans"


def test_apply_attr_translations_overlays_known_attr_and_keeps_custom():
    attrs = [
        {"attr_id": "inst_name", "attr_name": "实例名", "attr_group": "基本信息"},
        {"attr_id": "custom_field", "attr_name": "用户自定义", "attr_group": "基本信息"},
    ]

    result = {item["attr_id"]: item for item in apply_attr_translations(attrs, "host", "en")}

    assert result["inst_name"]["attr_name"] == "Name"
    assert result["custom_field"]["attr_name"] == "用户自定义"
    assert result["inst_name"]["attr_group"] == "基本信息"


def test_apply_attr_translations_zh_cn_uses_hans_catalog():
    attrs = [{"attr_id": "inst_name", "attr_name": "Name", "attr_type": "str"}]
    result = apply_attr_translations(attrs, "host", "zh-CN")
    assert result[0]["attr_name"] == "实例名"


def test_catalog_display_name_uses_translation_until_user_renames():
    assert catalog_display_name("MODEL", "host", "主机", language="en") == "Host"
    assert catalog_display_name("MODEL", "host", "服务器", customized=True, language="en") == "服务器"
    assert catalog_display_name("CLASSIFICATION", "device", "物理设备", language="en") == "Device"
    assert catalog_display_name("CLASSIFICATION", "device", "我的设备", customized=True, language="zh-Hans") == "我的设备"


def test_mark_catalog_name_customized_keeps_seed_echo_for_groups_only():
    current = {"is_pre": True, "classification_name": "物理设备", "classification_id": "device"}
    echoed = mark_catalog_name_customized(
        current,
        {"classification_name": "Device"},
        kind="CLASSIFICATION",
        key="device",
        name_field="classification_name",
        flag_field="classification_name_customized",
        preserve_seed_echo=True,
    )
    assert echoed["classification_name"] == "物理设备"
    assert "classification_name_customized" not in echoed

    renamed = mark_catalog_name_customized(
        {"is_pre": True, "model_name": "主机", "model_id": "host"},
        {"model_name": "Host"},
        kind="MODEL",
        key="host",
        name_field="model_name",
        flag_field="model_name_customized",
    )
    assert renamed["model_name"] == "Host"
    assert renamed["model_name_customized"] is True


def test_group_display_name_builtin_and_custom():
    assert group_display_name("基本信息", "en") == "Basic Information"
    assert group_display_name("技术信息", "en") == "Technical Information"
    assert group_display_name("管理信息", "en") == "Management Information"
    assert group_display_name("自动发现信息", "en") == "Auto Discovery"
    assert group_display_name("基本信息", "zh-Hans") == "基本信息"
    assert group_display_name("我的分组", "en") == "我的分组"


def test_change_record_labels_follow_locale():
    en = SettingLanguage("en")
    zh = SettingLanguage("zh-Hans")
    assert en.get_val("ChangeRecordScenario", "ordinary_attribute_change") == "Attribute Change"
    assert en.get_val("ChangeRecordScenario", "collect_automation_change") == "Auto Collection"
    assert zh.get_val("ChangeRecordScenario", "ordinary_attribute_change") == "普通属性变更"
    assert en.get_val("ChangeRecordType", "update_entity") == "Update"
    assert model_object_display_name("资产实例", "en") == "Asset Instance"
    assert model_object_display_name("资产实例", "zh-Hans") == "资产实例"
    assert model_object_display_name("阿里云ECS", "en") == "阿里云ECS"


def test_host_and_mssql_attr_names_resolve_in_both_languages():
    cases = [
        ("host", "host_outerip", "zh-Hans", "外网IP"),
        ("host", "host_outerip", "en", "Outerip"),
        ("host", "cpu", "zh-Hans", "CPU"),
        ("host", "cpu", "en", "CPU"),
        ("host", "cpu_module", "zh-Hans", "CPU模块"),
        ("host", "cpu_module", "en", "CPU Module"),
        ("host", "mac", "zh-Hans", "MAC"),
        ("host", "mac", "en", "MAC"),
        ("host", "operatr", "zh-Hans", "主要维护人"),
        ("host", "operatr", "en", "Operator"),
        ("mssql", "max_connect", "zh-Hans", "最大连接数"),
        ("mssql", "max_connect", "en", "MAX Connect"),
        ("mssql", "max_memory", "zh-Hans", "最大内存"),
        ("mssql", "max_memory", "en", "MAX Memory"),
    ]
    for model_id, attr_id, language, expected in cases:
        attrs = [{"attr_id": attr_id, "attr_name": "stored"}]
        result = apply_attr_translations(attrs, model_id, language)
        assert result[0]["attr_name"] == expected, (model_id, attr_id, language)
