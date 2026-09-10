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
