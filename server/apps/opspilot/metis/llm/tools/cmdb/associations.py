from typing import Any, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _resolve_allow_write,
    _resolve_team_context,
    build_permission_map,
    ensure_instance_permission,
    ensure_model_permission,
    ensure_write_allowed,
    wrap_error,
    wrap_success,
)


@tool(description="List associations for a model.")
def cmdb_list_model_associations(
    model_id: str,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise ValueError("model not found")
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="model",
            model_id=model_id,
        )
        ensure_model_permission(user, model_info, permissions_map, operator="View")
        associations = ModelManage.model_association_search(model_id)
        return wrap_success(associations)
    except Exception as e:
        logger.exception("cmdb_list_model_associations failed: %s", e)
        return wrap_error(str(e))


@tool(description="List associations for an instance.")
def cmdb_list_instance_associations(
    model_id: str,
    inst_id: int,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
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
            model_id=model_id,
        )
        ensure_instance_permission(user, instance, permissions_map, operator="View")
        associations = InstanceManage.instance_association(model_id, int(inst_id))
        return wrap_success(associations)
    except Exception as e:
        logger.exception("cmdb_list_instance_associations failed: %s", e)
        return wrap_error(str(e))


@tool(description="List instances associated with an instance.")
def cmdb_list_associated_instances(
    model_id: str,
    inst_id: int,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
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
            model_id=model_id,
        )
        ensure_instance_permission(user, instance, permissions_map, operator="View")
        associations = InstanceManage.instance_association_instance_list(model_id, int(inst_id))
        return wrap_success(associations)
    except Exception as e:
        logger.exception("cmdb_list_associated_instances failed: %s", e)
        return wrap_error(str(e))


@tool(description="Create an instance association.")
def cmdb_create_instance_association(
    data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    try:
        if not isinstance(data, dict):
            raise ValueError("data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = InstanceManage.instance_association_create(data, user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_create_instance_association failed: %s", e)
        return wrap_error(str(e))


@tool(description="Delete an instance association.")
def cmdb_delete_instance_association(
    asso_id: int,
    allow_write: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        InstanceManage.instance_association_delete(int(asso_id), user.username)
        return wrap_success({"asso_id": asso_id, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_delete_instance_association failed: %s", e)
        return wrap_error(str(e))
