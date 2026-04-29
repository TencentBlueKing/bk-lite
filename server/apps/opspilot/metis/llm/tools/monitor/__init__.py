"""Monitor built-in toolset backed by Monitor RPC/NATS."""

from apps.opspilot.metis.llm.tools.monitor.alerts import monitor_list_active_alerts, monitor_query_alert_segments
from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_list_instance_metrics, monitor_list_object_metrics, monitor_query_metric_data
from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances, monitor_list_objects

CONSTRUCTOR_PARAMS = [
    {"name": "username", "type": "string", "required": True, "description": "登录账号"},
    {"name": "password", "type": "password", "required": True, "description": "登录密码"},
    {"name": "domain", "type": "string", "required": False, "description": "可选用户域，默认 domain.com"},
    {"name": "team_id", "type": "integer", "required": False, "description": "可选组织ID，由前端team接口选择后传入"},
]

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "monitor_list_objects",
    "monitor_list_object_instances",
    "monitor_list_object_metrics",
    "monitor_list_instance_metrics",
    "monitor_query_metric_data",
    "monitor_list_active_alerts",
    "monitor_query_alert_segments",
]
