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
