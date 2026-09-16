"""SSL 证书采集对象树、语言包与协议插件单元测试（_pure：不依赖 DB/IO）。

验证：COLLECT_OBJ_TREE 含 certificate/ssl_cer 条目，中英文语言包覆盖分组与插件；
采集按实例名回写时效字段，不映射域名，立即清理也不删除未见实例。
"""
from types import SimpleNamespace

import pytest

from apps.cmdb.constants.constants import DataCleanupStrategy
from apps.cmdb.tests.test_collect_management_service import FakeGraph, _mgmt

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


def test_ssl_cer_plugin_does_not_use_ip_port_identity():
    from apps.cmdb.collection.plugins.community.protocol.ssl_cer import SslCerCollectionPlugin

    assert SslCerCollectionPlugin.field_mapping["inst_name"] == "inst_name"
    assert "domain" not in SslCerCollectionPlugin.field_mapping
    assert SslCerCollectionPlugin._MODEL_ID is None


def test_ssl_cer_format_metrics_keeps_instance_name():
    from apps.cmdb.collection.plugins.community.protocol.ssl_cer import SslCerCollectionPlugin

    plugin = SslCerCollectionPlugin(
        "unused",
        None,
        9,
        collect_inst=SimpleNamespace(model_id="ssl_cer"),
    )
    plugin.collection_metrics_dict = {
        "ssl_cer_info_gauge": [
            {
                "inst_name": "rex-test",
                "domain": "www.example.com",
                "issuer": "CN=Example CA",
                "create_time": "2024-01-01 00:00:00",
                "expired_time": "2025-01-01 00:00:00",
                "ip_addr": "10.0.0.1",
                "port": "443",
            }
        ]
    }
    plugin.format_metrics()
    row = plugin.result["ssl_cer"][0]
    assert row["inst_name"] == "rex-test"
    assert "T" in row["create_time"]
    assert "domain" not in row


def test_ssl_cer_immediately_cleanup_does_not_delete_missing_instances(monkeypatch):
    from apps.cmdb.collection.plugins.community.protocol.ssl_cer import SslCerCollectionPlugin

    plugin = SslCerCollectionPlugin(
        "unused",
        None,
        9,
        collect_inst=SimpleNamespace(model_id="ssl_cer"),
    )
    m = _mgmt(
        monkeypatch,
        FakeGraph(),
        [
            {"inst_name": "keep-cert", "_id": 1},
            {"inst_name": "missing-cert", "_id": 2},
        ],
        [{"inst_name": "keep-cert"}],
        collect_plugin=plugin,
        data_cleanup_strategy=DataCleanupStrategy.IMMEDIATELY,
    )
    assert m.delete_list == []
