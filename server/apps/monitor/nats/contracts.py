"""监控 NATS 对外契约。

该模块不得产生 handler 注册副作用，供分阶段拆分时稳定校验既有 subject。
"""

MONITOR_NATS_HANDLER_NAMES = frozenset(
    {
        "create_metric",
        "create_metric_group",
        "create_monitor_object",
        "create_monitor_object_type",
        "create_monitor_plugin",
        "create_monitor_policy",
        "delete_monitor_policy",
        "get_host_instance_list",
        "get_host_metric_range",
        "get_host_resource_snapshot",
        "get_host_resource_top",
        "get_monitor_statistics",
        "get_network_device_resource_top",
        "monitor_ingest_from_source",
        "monitor_instance_metrics",
        "monitor_metrics",
        "monitor_object_instance_count",
        "monitor_object_instances",
        "monitor_objects",
        "query_latest_active_alerts",
        "query_latest_interface_metrics",
        "query_monitor_alert_segments",
        "query_monitor_data_by_metric",
        "query_metric_range_scoped",
        "search_monitor_policies",
    }
)
