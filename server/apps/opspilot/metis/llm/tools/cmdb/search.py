from typing import Any, Dict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.cmdb.utils import call_cmdb_params, wrap_error


@tool(description="跨模型全文检索 CMDB 实例。")
def cmdb_fulltext_search(
    search: str,
    case_sensitive: bool = False,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not search:
        return wrap_error("search is required")
    return call_cmdb_params("fulltext_search", config, search=search, case_sensitive=case_sensitive)


@tool(description="跨模型全文检索统计。")
def cmdb_fulltext_search_stats(
    search: str,
    case_sensitive: bool = False,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not search:
        return wrap_error("search is required")
    return call_cmdb_params("fulltext_search_stats", config, search=search, case_sensitive=case_sensitive)


@tool(description="按模型全文检索 CMDB 实例。")
def cmdb_fulltext_search_by_model(
    search: str,
    model_id: str,
    page: int = 1,
    page_size: int = 10,
    case_sensitive: bool = False,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not search:
        return wrap_error("search is required")
    if not model_id:
        return wrap_error("model_id is required")
    return call_cmdb_params(
        "fulltext_search_by_model",
        config,
        search=search,
        model_id=model_id,
        page=int(page),
        page_size=int(page_size),
        case_sensitive=case_sensitive,
    )
