"""Monitor built-in toolset backed by Monitor RPC/NATS.

用当前用户身份查询 BK-Lite 监控数据：已纳管对象与实例、指标定义与时序、
主机资源快照，以及监控策略产生的活跃告警与告警历史。
覆盖主机、Kubernetes、中间件等对象上的 CPU/内存/磁盘/业务等指标。

说明：本模块 docstring 仅供 parse_tools_yml 入库与界面展示；
给大模型的调用约束写在各 @tool(description=...) 中，运行时从代码加载。
"""

from apps.opspilot.metis.llm.tools.monitor.alerts import monitor_list_active_alerts, monitor_query_alert_segments
from apps.opspilot.metis.llm.tools.monitor.metrics import (
    monitor_get_host_resource_snapshot,
    monitor_list_instance_metrics,
    monitor_list_object_metrics,
    monitor_query_metric_data,
)
from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances, monitor_list_objects

CONSTRUCTOR_PARAMS = []

__all__ = [
    "CONSTRUCTOR_PARAMS",
    "monitor_list_objects",
    "monitor_list_object_instances",
    "monitor_list_object_metrics",
    "monitor_list_instance_metrics",
    "monitor_query_metric_data",
    "monitor_get_host_resource_snapshot",
    "monitor_list_active_alerts",
    "monitor_query_alert_segments",
]
