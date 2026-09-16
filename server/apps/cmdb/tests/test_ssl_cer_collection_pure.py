"""SSL 证书采集对象树与语言包单元测试（_pure：不依赖 DB/IO）。

验证：COLLECT_OBJ_TREE 含 certificate/ssl_cer 条目，中英文语言包覆盖分组与插件。
"""
import pytest

pytestmark = pytest.mark.unit


def test_ssl_cer_in_collect_object_tree():
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    groups = [grp for grp in COLLECT_OBJ_TREE if grp.get("id") == "certificate"]
    assert groups
    children = groups[0]["children"]
    entry = next(item for item in children if item["id"] == "ssl_cer")
    assert entry["model_id"] == "ssl_cer"
    assert entry["task_type"] == "protocol"
    assert entry["type"] == "protocol"
    assert entry["encrypted_fields"] == []


def test_ssl_cer_collect_language_keys_exist():
    from apps.core.utils.loader import LanguageLoader

    en = LanguageLoader("cmdb", "en").translations
    zh = LanguageLoader("cmdb", "zh-Hans").translations
    assert en["COLLECT_GROUP"]["certificate"]
    assert zh["COLLECT_GROUP"]["certificate"]
    assert en["COLLECT_PLUGIN"]["ssl_cer"]["name"]
    assert en["COLLECT_PLUGIN"]["ssl_cer"]["desc"]
    assert zh["COLLECT_PLUGIN"]["ssl_cer"]["name"]
    assert zh["COLLECT_PLUGIN"]["ssl_cer"]["desc"]
