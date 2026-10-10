"""CMDB 内置属性/分组展示名覆盖（不依赖 Django migrate）。"""

import pytest

from apps.cmdb.language.service import apply_attr_translations, group_display_name, normalize_cmdb_language

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


def test_group_display_name_builtin_and_custom():
    assert group_display_name("基本信息", "en") == "Basic Information"
    assert group_display_name("基本信息", "zh-Hans") == "基本信息"
    assert group_display_name("我的分组", "en") == "我的分组"


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
