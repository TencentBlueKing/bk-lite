"""Elasticsearch 运维工具模块

这个模块提供 Elasticsearch 相关的内置工具集，包含集群健康、索引、文档、搜索、mapping 等能力。
"""

from apps.opspilot.metis.llm.tools.elasticsearch.aliases import es_alias_exists, es_get_alias, es_update_aliases
from apps.opspilot.metis.llm.tools.elasticsearch.cat import (
    es_cat_aliases,
    es_cat_allocation,
    es_cat_indices,
    es_cat_nodes,
    es_cat_recovery,
    es_cat_shards,
)
from apps.opspilot.metis.llm.tools.elasticsearch.cluster import es_cluster_health, es_cluster_stats, es_info, es_nodes_info, es_nodes_stats, es_ping
from apps.opspilot.metis.llm.tools.elasticsearch.documents import (
    es_bulk,
    es_delete_document,
    es_get_document,
    es_index_document,
    es_multi_get,
    es_update_document,
)
from apps.opspilot.metis.llm.tools.elasticsearch.indices import (
    es_close_index,
    es_create_index,
    es_delete_index,
    es_forcemerge_index,
    es_get_index,
    es_index_exists,
    es_index_stats,
    es_list_indices,
    es_open_index,
    es_refresh_index,
)
from apps.opspilot.metis.llm.tools.elasticsearch.ingest import es_delete_pipeline, es_get_pipeline, es_put_pipeline, es_simulate_pipeline
from apps.opspilot.metis.llm.tools.elasticsearch.mappings import es_field_caps, es_get_mapping, es_get_settings, es_put_mapping, es_put_settings
from apps.opspilot.metis.llm.tools.elasticsearch.search import (
    es_count,
    es_explain,
    es_knn_search,
    es_multi_search,
    es_search,
    es_search_template,
    es_validate_query,
)
from apps.opspilot.metis.llm.tools.elasticsearch.snapshots import (
    es_create_snapshot,
    es_create_snapshot_repository,
    es_get_snapshot_repositories,
    es_get_snapshots,
    es_restore_snapshot,
)

CONSTRUCTOR_PARAMS = [
    {"name": "es_instances", "type": "string", "required": False, "description": "Elasticsearch多实例JSON配置"},
    {"name": "es_default_instance_id", "type": "string", "required": False, "description": "默认Elasticsearch实例ID"},
]

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "es_ping",
    "es_info",
    "es_cluster_health",
    "es_cluster_stats",
    "es_nodes_info",
    "es_nodes_stats",
    "es_get_alias",
    "es_alias_exists",
    "es_update_aliases",
    "es_cat_indices",
    "es_cat_shards",
    "es_cat_nodes",
    "es_cat_aliases",
    "es_cat_allocation",
    "es_cat_recovery",
    "es_list_indices",
    "es_get_index",
    "es_index_exists",
    "es_create_index",
    "es_delete_index",
    "es_open_index",
    "es_close_index",
    "es_refresh_index",
    "es_forcemerge_index",
    "es_index_stats",
    "es_search",
    "es_count",
    "es_get_document",
    "es_index_document",
    "es_update_document",
    "es_delete_document",
    "es_multi_get",
    "es_bulk",
    "es_get_mapping",
    "es_get_settings",
    "es_put_mapping",
    "es_put_settings",
    "es_field_caps",
    "es_get_pipeline",
    "es_put_pipeline",
    "es_delete_pipeline",
    "es_simulate_pipeline",
    "es_get_snapshot_repositories",
    "es_create_snapshot_repository",
    "es_get_snapshots",
    "es_create_snapshot",
    "es_restore_snapshot",
    "es_validate_query",
    "es_multi_search",
    "es_explain",
    "es_search_template",
    "es_knn_search",
]
