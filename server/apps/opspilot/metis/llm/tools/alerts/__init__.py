"""Alert Center built-in toolset.

用当前用户身份查询统一告警中心的告警列表、详情与关联事件。只读，不支持认领或关闭。

说明：本模块 docstring 仅供 parse_tools_yml 入库与界面展示；
给大模型的调用约束写在各 @tool(description=...) 中，运行时从代码加载。
"""

from apps.opspilot.metis.llm.tools.alerts.queries import alerts_get_alert_detail, alerts_list_alert_events, alerts_list_alerts
from apps.opspilot.utils.db_cleanup import wrap_langchain_tool

_ALERTS_TOOLS = (
    alerts_list_alerts,
    alerts_get_alert_detail,
    alerts_list_alert_events,
)
for _tool in _ALERTS_TOOLS:
    wrap_langchain_tool(_tool)
del _tool, _ALERTS_TOOLS

CONSTRUCTOR_PARAMS = []

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "alerts_list_alerts",
    "alerts_get_alert_detail",
    "alerts_list_alert_events",
]
