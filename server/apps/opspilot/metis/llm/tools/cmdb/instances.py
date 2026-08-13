from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.instance import InstanceManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _get_user_group_ids,
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
from apps.system_mgmt.utils.group_utils import GroupUtils


def _serialize_instance(instance: dict) -> dict:
    aliases = {"_creator": "creator", "_created_at": "created_at", "_updated_at": "updated_at"}
    return {aliases.get(key, key): value for key, value in (instance or {}).items() if key not in {"_id", "_labels", "permission"}}


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
        return wrap_success({"insts": [_serialize_instance(item) for item in inst_list], "count": count})
    except Exception as e:
        logger.exception("cmdb_search_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Get a CMDB instance by UUID.")
def cmdb_get_instance(
    inst_uuid: str,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
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
        return wrap_success(_serialize_instance(instance))
    except Exception as e:
        logger.exception("cmdb_get_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Create a CMDB instance.")
def cmdb_create_instance(
    model_id: str,
    instance_info: Dict[str, Any],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        if not isinstance(instance_info, dict):
            raise ValueError("instance_info must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_group_ids = _get_user_group_ids(user)
        if getattr(user, "is_superuser", False):
            allowed_org_ids = GroupUtils.get_group_with_descendants(resolved_team) if resolved_children else [resolved_team]
        elif resolved_children:
            allowed_org_ids = GroupUtils.get_user_authorized_child_groups(
                user_group_ids,
                resolved_team,
                include_children=True,
            )
        else:
            allowed_org_ids = [resolved_team] if resolved_team in user_group_ids else []
        result = InstanceManage.instance_create(
            model_id,
            instance_info,
            user.username,
            allowed_org_ids=allowed_org_ids,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_create_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Update a CMDB instance by UUID.")
def cmdb_update_instance(
    inst_uuid: str,
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
        result = InstanceManage.instance_update_by_uuid(
            user_groups,
            user.roles,
            inst_uuid,
            update_data,
            user.username,
        )
        return wrap_success(_serialize_instance(result))
    except Exception as e:
        logger.exception("cmdb_update_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Batch update CMDB instances.")
def cmdb_batch_update_instances(
    inst_uuids: List[str],
    update_data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not inst_uuids:
            raise ValueError("inst_uuids is required")
        if not isinstance(update_data, dict):
            raise ValueError("update_data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        result = InstanceManage.batch_instance_update_by_uuids(
            user_groups,
            user.roles,
            inst_uuids,
            update_data,
            user.username,
        )
        return wrap_success([_serialize_instance(item) for item in result])
    except Exception as e:
        logger.exception("cmdb_batch_update_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Delete a CMDB instance by UUID.")
def cmdb_delete_instance(
    inst_uuid: str,
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
        InstanceManage.instance_batch_delete_by_uuids(
            user_groups,
            user.roles,
            [inst_uuid],
            user.username,
        )
        return wrap_success({"inst_uuid": inst_uuid, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_delete_instance failed: %s", e)
        return wrap_error(str(e))


@tool(description="Batch delete CMDB instances.")
def cmdb_batch_delete_instances(
    inst_uuids: List[str],
    allow_write: Optional[bool] = None,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not inst_uuids:
            raise ValueError("inst_uuids is required")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        user_groups = build_user_groups(user, resolved_team, resolved_children)
        InstanceManage.instance_batch_delete_by_uuids(
            user_groups,
            user.roles,
            inst_uuids,
            user.username,
        )
        return wrap_success({"inst_uuids": inst_uuids, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_batch_delete_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Query CMDB topology starting from an instance.")
def cmdb_topo_search(
    inst_uuid: str,
    depth: int = 3,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
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
        result = InstanceManage.topo_search_lite_by_uuid(
            inst_uuid,
            depth=int(depth),
            permission_map=permissions_map,
            user=user,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_topo_search failed: %s", e)
        return wrap_error(str(e))


@tool(description="Expand CMDB topology for an instance.")
def cmdb_topo_expand(
    inst_uuid: str,
    parent_uuids: List[str],
    depth: int = 2,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not isinstance(parent_uuids, list):
            raise ValueError("parent_uuids must be a list")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        instance = InstanceManage.query_entity_by_uuid(inst_uuid)
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
        result = InstanceManage.topo_search_expand_by_uuid(
            inst_uuid,
            parent_uuids,
            depth=int(depth),
            permission_map=permissions_map,
            user=user,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_topo_expand failed: %s", e)
        return wrap_error(str(e))
