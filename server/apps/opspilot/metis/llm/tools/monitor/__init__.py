"""Monitor built-in toolset backed by Monitor RPC/NATS.

【主机CPU使用率】BK-Lite 已纳管监控：对象→实例(主机名)→指标名→时序。
支持按主机名查 CPU/内存/磁盘与告警；不提供 SSH 或本机 top/htop。
"""

from apps.opspilot.metis.llm.tools.monitor.alerts import monitor_list_active_alerts, monitor_query_alert_segments
from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_list_instance_metrics, monitor_list_object_metrics, monitor_query_metric_data
from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances, monitor_list_objects

CONSTRUCTOR_PARAMS = []

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
