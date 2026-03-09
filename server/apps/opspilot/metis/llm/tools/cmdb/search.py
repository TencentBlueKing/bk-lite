from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.cmdb.services.instance import InstanceManage
from apps.core.logger import cmdb_logger as logger
from apps.opspilot.metis.llm.tools.cmdb.utils import (
    _get_user_from_config,
    _resolve_team_context,
    build_permission_map,
    wrap_error,
    wrap_success,
)


@tool(description="Full-text search CMDB instances.")
def cmdb_fulltext_search(
    search: str,
    case_sensitive: bool = False,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not search:
            raise ValueError("search is required")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id="",
        )
        result = InstanceManage.fulltext_search(
            search=search,
            permission_map=permissions_map,
            creator=user.username,
            case_sensitive=case_sensitive,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_fulltext_search failed: %s", e)
        return wrap_error(str(e))


@tool(description="Get CMDB full-text search stats.")
def cmdb_fulltext_search_stats(
    search: str,
    case_sensitive: bool = False,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not search:
            raise ValueError("search is required")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id="",
        )
        result = InstanceManage.fulltext_search_stats(
            search=search,
            permission_map=permissions_map,
            creator=user.username,
            case_sensitive=case_sensitive,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_fulltext_search_stats failed: %s", e)
        return wrap_error(str(e))


@tool(description="Full-text search CMDB instances by model.")
def cmdb_fulltext_search_by_model(
    search: str,
    model_id: str,
    page: int = 1,
    page_size: int = 10,
    case_sensitive: bool = False,
    team_id: Optional[int] = None,
    include_children: Optional[bool] = None,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    try:
        if not search:
            raise ValueError("search is required")
        if not model_id:
            raise ValueError("model_id is required")
        user = _get_user_from_config(config)
        resolved_team, resolved_children = _resolve_team_context(user, config, team_id, include_children)
        permissions_map = build_permission_map(
            user,
            current_team=resolved_team,
            include_children=resolved_children,
            permission_type="instances",
            model_id="",
        )
        result = InstanceManage.fulltext_search_by_model(
            search=search,
            model_id=model_id,
            permission_map=permissions_map,
            creator=user.username,
            page=int(page),
            page_size=int(page_size),
            case_sensitive=case_sensitive,
        )
        return wrap_success(result)
    except Exception as e:
        logger.exception("cmdb_fulltext_search_by_model failed: %s", e)
        return wrap_error(str(e))
