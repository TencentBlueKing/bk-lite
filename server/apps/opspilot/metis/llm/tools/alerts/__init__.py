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
