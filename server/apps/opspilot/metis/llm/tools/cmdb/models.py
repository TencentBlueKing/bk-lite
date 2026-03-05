from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _resolve_allow_write,
    _resolve_team_context,
    build_permission_map,
    ensure_model_permission,
    ensure_write_allowed,
    wrap_error,
    wrap_success,
)
from apps.cmdb.constants.constants import VIEW


@tool(description="List CMDB models accessible to user.")
def cmdb_list_models(
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="model",
            model_id="",
        )
        models = ModelManage.search_model(language=user.locale, permissions_map=permissions_map)

        grouped_models: Dict[str, list] = {}
        for model in models:
            category = str(model.get("classification_id") or "")
            model_id = str(model.get("model_id") or "")
            model_name = str(model.get("model_name") or "")
            if not category or not model_id:
                continue

            grouped_models.setdefault(category, []).append({"id": model_id, "name": model_name})

        compact_models = {
            "model_categories": [
                {"category": category, "models": model_list}
                for category, model_list in grouped_models.items()
            ]
        }
        return wrap_success(compact_models)
    except Exception as e:
        logger.exception("cmdb_list_models failed: %s", e)
        logger.exception(config)
        return wrap_error(str(e))


@tool(description="Get CMDB model details by ID.")
def cmdb_get_model_info(
    model_id: str,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
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
        ensure_model_permission(user, model_info, permissions_map, operator=VIEW)
        return wrap_success(model_info)
    except Exception as e:
        logger.exception("cmdb_get_model_info failed: %s", e)
        return wrap_error(str(e))


@tool(description="List model attributes by model ID.")
def cmdb_list_model_attrs(
    model_id: str,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
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
        ensure_model_permission(user, model_info, permissions_map, operator=VIEW)
        attrs = ModelManage.search_model_attr(model_id, user.locale)
        attrs = [attr for attr in attrs if not attr.get("is_display_field")]
        return wrap_success(attrs)
    except Exception as e:
        logger.exception("cmdb_list_model_attrs failed: %s", e)
        return wrap_error(str(e))


@tool(description="Create a CMDB model.")
def cmdb_create_model(
    model_data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not isinstance(model_data, dict):
            raise ValueError("model_data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = ModelManage.create_model(model_data, username=user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_create_model failed: %s", e)
        return wrap_error(str(e))


@tool(description="Update a CMDB model.")
def cmdb_update_model(
    model_id: str,
    update_data: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        if not isinstance(update_data, dict):
            raise ValueError("update_data must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise ValueError("model not found")
        update_payload = {**update_data, "model_id": model_id}
        model_db_id = model_info.get("_id")
        if not isinstance(model_db_id, int):
            raise ValueError("model id is invalid")
        result = ModelManage.update_model(model_db_id, update_payload)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_update_model failed: %s", e)
        return wrap_error(str(e))


@tool(description="Delete a CMDB model.")
def cmdb_delete_model(
    model_id: str,
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise ValueError("model not found")
        ModelManage.check_model_exist_association(model_id)
        ModelManage.check_model_exist_inst(model_id)
        model_db_id = model_info.get("_id")
        if not isinstance(model_db_id, int):
            raise ValueError("model id is invalid")
        ModelManage.delete_model(model_db_id)
        return wrap_success({"model_id": model_id, "deleted": True})
    except Exception as e:
        logger.exception("cmdb_delete_model failed: %s", e)
        return wrap_error(str(e))


@tool(description="Create a model attribute.")
def cmdb_create_model_attr(
    model_id: str,
    attr_info: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        if not isinstance(attr_info, dict):
            raise ValueError("attr_info must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = ModelManage.create_model_attr(model_id, attr_info, username=user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_create_model_attr failed: %s", e)
        return wrap_error(str(e))


@tool(description="Update a model attribute.")
def cmdb_update_model_attr(
    model_id: str,
    attr_info: Dict[str, Any],
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id:
            raise ValueError("model_id is required")
        if not isinstance(attr_info, dict):
            raise ValueError("attr_info must be a dict")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = ModelManage.update_model_attr(model_id, attr_info, username=user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_update_model_attr failed: %s", e)
        return wrap_error(str(e))


@tool(description="Delete a model attribute.")
def cmdb_delete_model_attr(
    model_id: str,
    attr_id: str,
    allow_write: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not model_id or not attr_id:
            raise ValueError("model_id and attr_id are required")
        user = _get_user_from_config(config)
        ensure_write_allowed(user, _resolve_allow_write(config, allow_write))
        result = ModelManage.delete_model_attr(model_id, attr_id, username=user.username)
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_delete_model_attr failed: %s", e)
        return wrap_error(str(e))
