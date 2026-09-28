"""Log Center built-in toolset.

用当前用户身份查询日志：列出可访问分组，按关键词做结构化检索，复杂场景可用原生 LogsQL。

说明：本模块 docstring 仅供 parse_tools_yml 入库与界面展示；
给大模型的调用约束写在各 @tool(description=...) 中，运行时从代码加载。
"""

from apps.opspilot.metis.llm.tools.log.queries import log_list_groups, log_search_raw, log_search_structured
from apps.opspilot.utils.db_cleanup import wrap_langchain_tool

_LOG_TOOLS = (
    log_list_groups,
    log_search_structured,
    log_search_raw,
)
for _tool in _LOG_TOOLS:
    wrap_langchain_tool(_tool)
del _tool, _LOG_TOOLS

CONSTRUCTOR_PARAMS = []

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "log_list_groups",
    "log_search_structured",
    "log_search_raw",
]
