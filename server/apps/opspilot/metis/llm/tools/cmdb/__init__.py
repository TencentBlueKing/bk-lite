"""CMDB built-in toolset.

用当前用户身份查询和变更 BK-Lite CMDB 资产：模型、实例增删改查、关联与拓扑、全文检索。
权限由服务端按调用方身份校验。

说明：本模块 docstring 仅供 parse_tools_yml 入库与界面展示；
给大模型的调用约束写在各 @tool(description=...) 中，运行时从代码加载。
"""

from apps.opspilot.metis.llm.tools.cmdb.associations import (
    cmdb_create_instance_association,
    cmdb_delete_instance_association,
    cmdb_list_associated_instances,
    cmdb_list_instance_associations,
    cmdb_list_model_associations,
)
from apps.opspilot.metis.llm.tools.cmdb.instances import (
    cmdb_batch_delete_instances,
    cmdb_batch_update_instances,
    cmdb_create_instance,
    cmdb_delete_instance,
    cmdb_get_instance,
    cmdb_get_monitor_ids,
    cmdb_search_instances,
    cmdb_topo_expand,
    cmdb_topo_search,
    cmdb_update_instance,
)
from apps.opspilot.metis.llm.tools.cmdb.models import cmdb_get_model_info, cmdb_list_model_attrs, cmdb_list_models
from apps.opspilot.metis.llm.tools.cmdb.search import cmdb_fulltext_search, cmdb_fulltext_search_by_model, cmdb_fulltext_search_stats
from apps.opspilot.utils.db_cleanup import wrap_langchain_tool

_CMDB_TOOLS = (
    cmdb_list_models,
    cmdb_get_model_info,
    cmdb_list_model_attrs,
    cmdb_search_instances,
    cmdb_get_instance,
    cmdb_get_monitor_ids,
    cmdb_create_instance,
    cmdb_update_instance,
    cmdb_batch_update_instances,
    cmdb_delete_instance,
    cmdb_batch_delete_instances,
    cmdb_topo_search,
    cmdb_topo_expand,
    cmdb_list_model_associations,
    cmdb_list_instance_associations,
    cmdb_list_associated_instances,
    cmdb_create_instance_association,
    cmdb_delete_instance_association,
    cmdb_fulltext_search,
    cmdb_fulltext_search_stats,
    cmdb_fulltext_search_by_model,
)
for _tool in _CMDB_TOOLS:
    wrap_langchain_tool(_tool)
del _tool, _CMDB_TOOLS

CONSTRUCTOR_PARAMS = []

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "cmdb_list_models",
    "cmdb_get_model_info",
    "cmdb_list_model_attrs",
    "cmdb_search_instances",
    "cmdb_get_instance",
    "cmdb_get_monitor_ids",
    "cmdb_create_instance",
    "cmdb_update_instance",
    "cmdb_batch_update_instances",
    "cmdb_delete_instance",
    "cmdb_batch_delete_instances",
    "cmdb_topo_search",
    "cmdb_topo_expand",
    "cmdb_list_model_associations",
    "cmdb_list_instance_associations",
    "cmdb_list_associated_instances",
    "cmdb_create_instance_association",
    "cmdb_delete_instance_association",
    "cmdb_fulltext_search",
    "cmdb_fulltext_search_stats",
    "cmdb_fulltext_search_by_model",
]
