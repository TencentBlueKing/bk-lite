"""MinIO 采集插件单元测试（_pure：不依赖 DB/IO）。

验证：插件契约、field_mapping 覆盖模型字段、自动注册、字段映射逻辑。
MinIO 走中间件脚本采集（MIDDLEWARE/JOB），对齐 Nginx/Kafka。
"""
import pytest

MODEL_ATTRS = (
    "inst_name", "ip_addr", "port", "version", "bin_path",
    "data_path", "conf_path", "console_port", "deploy_mode",
    "region", "start_args",
)


def test_minio_plugin_contract():
    from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin
    from apps.cmdb.constants.constants import CollectPluginTypes

    assert MinioCollectionPlugin.supported_model_id == "minio"
    assert MinioCollectionPlugin.supported_task_type == CollectPluginTypes.MIDDLEWARE
    assert MinioCollectionPlugin.metric_names == ("minio_info_gauge",)


def test_minio_field_mapping_covers_model_attrs():
    from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin

    fm = MinioCollectionPlugin.field_mapping
    for attr in MODEL_ATTRS:
        assert attr in fm, f"field_mapping 缺少模型字段 {attr}"


def test_minio_registered_in_registry():
    from apps.cmdb.collection.plugins.community.middleware.minio import MinioCollectionPlugin
    from apps.cmdb.collection.plugins.registry import CollectionPluginRegistry
    from apps.cmdb.constants.constants import CollectPluginTypes

    plugin = CollectionPluginRegistry.get_plugin(CollectPluginTypes.MIDDLEWARE, "minio")
    assert plugin is MinioCollectionPlugin


def test_minio_in_collect_object_tree_with_beta():
    """采集对象树中应有 minio 条目，且名称带 Beta 标志。"""
    from apps.cmdb.constants.constants import COLLECT_OBJ_TREE

    entries = [c for grp in COLLECT_OBJ_TREE for c in grp.get("children", [])
               if c.get("model_id") == "minio"]
    assert entries, "COLLECT_OBJ_TREE 中缺少 minio"
    entry = entries[0]
    assert entry["task_type"] == "middleware"
    assert "beta" in entry["name"].lower(), f"minio 采集名称需带 Beta 标志，实际 {entry['name']!r}"
