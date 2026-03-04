from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.instance import InstanceManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _resolve_allow_write,
    _resolve_team_context,
    build_permission_map,
    build_user_groups,
    ensure_instance_permission,
    ensure_write_allowed,
    normalize_query_list,
    wrap_error,
    wrap_success,
)


@tool(description="Search instances for a model.")
def cmdb_search_instances(
    model_id: str,
    query_list: Optional[List[Dict[str, Any]]] = None,
    page: int = 1,
    page_size: int = 10,
    order: str = "",
    case_sensitive: bool = True,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        query_list = normalize_query_list(query_list)
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id=model_id,
        )
        inst_list, count = InstanceManage.instance_list(
            model_id=model_id,
            params=query_list,
            page=int(page),
            page_size=int(page_size),
            order=order,
            permission_map=permissions_map,
            creator=user.username,
            case_sensitive=case_sensitive,
        )
        return wrap_success({"insts": inst_list, "count": count})
    except Exception as e:
        logger.exception("cmdb_search_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Get a CMDB instance by ID.")
def cmdb_get_instance(
    inst_id: int,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise ValueError("instance not found")
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id=instance.get("model_id", ""),
        )
        ensure_instance_permission(user, instance, permissions_map, operator="View")
        return wrap_success(instance)
    except Exception as e:
        logger.exception("cmdb_get_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Create a CMDB instance.")
def cmdb_create_instance(
    model_id: str,
    instance_info: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        if not isinstance(instance_info, dict):
            raise ValueError("instance_info must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = InstanceManage.instance_create(model_id, instance_info, user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_create_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Update a CMDB instance by ID.")
def cmdb_update_instance(
    inst_id: int,
    update_data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not isinstance(update_data, dict):
            raise ValueError("update_data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        result = InstanceManage.instance_update(
            user_groups,
            user.roles,
            int(inst_id),
            update_data,
            user.username,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_update_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Batch update CMDB instances.")
def cmdb_batch_update_instances(
    inst_ids: List[int],
    update_data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not inst_ids:
            raise ValueError("inst_ids is required")
        if not isinstance(update_data, dict):
            raise ValueError("update_data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        result = InstanceManage.batch_instance_update(
            user_groups,
            user.roles,
            inst_ids,
            update_data,
            user.username,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_batch_update_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Delete a CMDB instance by ID.")
def cmdb_delete_instance(
    inst_id: int,
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        InstanceManage.instance_batch_delete(
            user_groups,
            user.roles,
            [int(inst_id)],
            user.username,
        )
        return wrap_success({"inst_id": inst_id, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_delete_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Batch delete CMDB instances.")
def cmdb_batch_delete_instances(
    inst_ids: List[int],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not inst_ids:
            raise ValueError("inst_ids is required")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        InstanceManage.instance_batch_delete(
            user_groups,
            user.roles,
            [int(i) for i in inst_ids],
            user.username,
        )
        return wrap_success({"inst_ids": inst_ids, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_batch_delete_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Query CMDB topology starting from an instance.")
def cmdb_topo_search(
    inst_id: int,
    depth: int = 3,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise ValueError("instance not found")
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id=instance.get("model_id", ""),
        )
        ensure_instance_permission(user, instance, permissions_map, operator="View")
        result = InstanceManage.topo_search_lite(int(inst_id), depth=int(depth))
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_topo_search failed: %s", e)
        return wrap_error(str(e))


@tool(description="Expand CMDB topology for an instance.")
def cmdb_topo_expand(
    inst_id: int,
    parent_ids: List[int],
    depth: int = 2,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not isinstance(parent_ids, list):
            raise ValueError("parent_ids must be a list")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_id(int(inst_id))
        if not instance:
            raise ValueError("instance not found")
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id=instance.get("model_id", ""),
        )
        ensure_instance_permission(user, instance, permissions_map, operator="View")
        result = InstanceManage.topo_search_expand(int(inst_id), parent_ids, depth=int(depth))
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_topo_expand failed: %s", e)
        return wrap_error(str(e))
