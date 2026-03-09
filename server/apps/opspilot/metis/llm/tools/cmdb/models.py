from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.model import ModelManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _resolve_team_context,
    build_permission_map,
    ensure_model_permission,
    wrap_error,
    wrap_success,
)
from apps.cmdb.constants.constants import VIEW


@tool(description="List CMDB models accessible to user.")
def cmdb_list_models(
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: Optional[RunnableConfig] = None,
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
        ensure_model_permission(user, model_info, permissions_map, operator=VIEW)
        attrs = ModelManage.search_model_attr(model_id, user.locale)
        attrs = [attr for attr in attrs if not attr.get("is_display_field")]
        return wrap_success(attrs)
    except Exception as e:
        logger.exception("cmdb_list_model_attrs failed: %s", e)
        return wrap_error(str(e))
