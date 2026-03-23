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
    cmdb_search_instances,
    cmdb_topo_expand,
    cmdb_topo_search,
    cmdb_update_instance,
)
from apps.opspilot.metis.llm.tools.cmdb.models import (
    cmdb_get_model_info,
    cmdb_list_model_attrs,
    cmdb_list_models,
)
from apps.opspilot.metis.llm.tools.cmdb.search import (
    cmdb_fulltext_search,
    cmdb_fulltext_search_by_model,
    cmdb_fulltext_search_stats,
)

CONSTRUCTOR_PARAMS = [
    {
        "name": "user_id",
        "type": "integer",
        "required": True,
        "description": "用户ID（必须提供）",
    },
    {
        "name": "team_id",
        "type": "integer",
        "required": False,
        "description": "组织ID，缺省使用当前用户组织",
    },
    {
        "name": "include_children",
        "type": "boolean",
        "required": False,
        "description": "是否包含子组织",
    },
    {
        "name": "allow_write",
        "type": "boolean",
        "required": False,
        "description": "是否允许写操作（默认false）",
    },
]

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "cmdb_list_models",
    "cmdb_get_model_info",
    "cmdb_list_model_attrs",
    "cmdb_search_instances",
    "cmdb_get_instance",
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
