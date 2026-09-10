"""配置采集对象树展示名覆盖（不改存储中文身份）。"""

import pytest

from apps.cmdb.constants.constants import COLLECT_OBJ_TREE
from apps.cmdb.language.service import apply_collect_tree_translations, overlay_collect_digest_message
from apps.core.utils.loader import LanguageLoader

pytestmark = pytest.mark.unit


def test_apply_collect_tree_translations_overlays_group_name_and_plugin_desc():
    tree = [
        {
            "id": "k8s",
            "name": "容器",
            "children": [
                {
                    "id": "k8s_cluster",
                    "name": "K8S",
                    "desc": "采集k8s集群核心对象node节点、命名空间、工作负载、pod",
                    "tag": ["apiserver"],
                }
            ],
        }
    ]

    result = apply_collect_tree_translations(tree, "en")

    assert result[0]["name"] == "Container"
    assert result[0]["children"][0]["name"] == "K8S"
    assert "Collect" in result[0]["children"][0]["desc"]
    assert "命名空间" not in result[0]["children"][0]["desc"]


def test_apply_collect_tree_translations_keeps_unknown_and_user_content():
    tree = [
        {
            "id": "custom_group",
            "name": "我的分类",
            "children": [
                {
                    "id": "custom_plugin",
                    "name": "自定义插件",
                    "desc": "用户自己写的说明",
                    "tag": ["国产"],
                }
            ],
        }
    ]

    result = apply_collect_tree_translations(tree, "en")

    assert result[0]["name"] == "我的分类"
    assert result[0]["children"][0]["name"] == "自定义插件"
    assert result[0]["children"][0]["desc"] == "用户自己写的说明"
    assert result[0]["children"][0]["tag"] == ["Domestic"]


def test_apply_collect_tree_translations_zh_keeps_community_identity():
    tree = [
        {
            "id": "host_manage",
            "name": "主机逻辑主机",
            "children": [{"id": "host", "name": "主机", "desc": "采集操作系统基础信息CPU内存等"}],
        }
    ]

    result = apply_collect_tree_translations(tree, "zh-CN")

    assert result[0]["name"] == "主机逻辑主机"
    assert result[0]["children"][0]["name"] == "主机"


def test_collect_language_covers_community_tree():
    en = LanguageLoader("cmdb", "en").translations
    zh = LanguageLoader("cmdb", "zh-Hans").translations
    groups = en.get("COLLECT_GROUP") or {}
    plugins = en.get("COLLECT_PLUGIN") or {}
    zh_groups = zh.get("COLLECT_GROUP") or {}
    zh_plugins = zh.get("COLLECT_PLUGIN") or {}

    missing = []
    for group in COLLECT_OBJ_TREE:
        gid = group["id"]
        if gid not in groups or gid not in zh_groups:
            missing.append(f"GROUP.{gid}")
        for child in group.get("children") or []:
            pid = child["id"]
            en_plugin = plugins.get(pid) or {}
            zh_plugin = zh_plugins.get(pid) or {}
            if not en_plugin.get("name") or not en_plugin.get("desc"):
                missing.append(f"PLUGIN.en.{pid}")
            if not zh_plugin.get("name") or not zh_plugin.get("desc"):
                missing.append(f"PLUGIN.zh.{pid}")

    assert missing == []
    assert groups["host_manage"] == "Logical Host"
    assert plugins["k8s_cluster"]["desc"].startswith("Collect")


def test_overlay_collect_digest_message_overlays_system_copy():
    digest = {
        "add": 0,
        "message": "未发现任何有效数据，请检查采集目标连通性、凭据与采集范围配置",
    }

    result = overlay_collect_digest_message(digest, "en")

    assert "No valid data found" in result["message"]
    assert digest["message"].startswith("未发现")
    assert overlay_collect_digest_message({"message": "用户自定义失败"}, "en")["message"] == "用户自定义失败"
