from typing import Any, Dict, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.cmdb.utils import call_cmdb_params, wrap_error


@tool(description="列出当前用户有权限的 CMDB 模型，按分类分组。")
def cmdb_list_models(
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    return call_cmdb_params("search_models_for_llm", config)


@tool(description="按 model_id 获取 CMDB 模型详情。")
def cmdb_get_model_info(
    model_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    return call_cmdb_params("get_model_info", config, model_id=model_id)


@tool(description="按 model_id 列出模型属性（不含展示字段）。")
def cmdb_list_model_attrs(
    model_id: str,
    config: RunnableConfig = None,
) -> Dict[str, Any]:
    if not model_id:
        return wrap_error("model_id is required")
    return call_cmdb_params("search_model_attrs_for_llm", config, model_id=model_id)
