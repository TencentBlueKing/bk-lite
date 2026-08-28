# -- coding: utf-8 --
# @File: health.py
# @Time: 2025/12/20
# @Author: AI Assistant
"""
健康检查和监控 API
提供统一采集运行时健康状态与容量监控信息
"""

from core.collection.application import get_collection_application
from sanic import Blueprint, response
from sanic.log import logger

health_router = Blueprint("health", url_prefix="/health")


@health_router.route("/", methods=["GET"])
async def health_check(request):
    """
    基础健康检查

    返回示例：
    {
        "status": "healthy",
        "timestamp": 1703001234567
    }
    """
    return response.json({"status": "ok", "timestamp": int(__import__("time").time() * 1000)})


@health_router.route("/ready", methods=["GET"])
async def readiness_check(request):
    """
    就绪检查 - 检查所有依赖服务是否可用

    用于 K8s readinessProbe 或负载均衡健康检查

    返回示例：
    {
        "ready": true,
        "checks": {
            "collection_runtime": "healthy",
            "redis": "connected"
        }
    }
    """
    checks = {}
    all_ready = True

    try:
        stats = await get_collection_application().stats()
        checks["collection_runtime"] = "healthy"
        checks["redis"] = "connected" if stats["healthy"] else "disconnected"
        if not stats["healthy"]:
            all_ready = False
    except Exception as e:
        checks["collection_runtime"] = f"error: {str(e)}"
        all_ready = False

    status_code = 200 if all_ready else 503

    return response.json(
        {
            "ready": all_ready,
            "checks": checks,
            "timestamp": int(__import__("time").time() * 1000),
        },
        status=status_code,
    )


@health_router.route("/stats", methods=["GET"])
async def runtime_stats(request):
    """
    统一采集运行时统计信息

    返回示例：
    {
        "healthy": true,
        "active_runs": 2,
        "active_targets": 120,
        "event_loop_lag_seconds": 0.003
    }
    """
    try:
        stats = await get_collection_application().stats()
        return response.json(stats)
    except Exception as e:
        logger.error(f"Failed to get collection runtime stats: {e}")
        return response.json(
            {
                "healthy": False,
                "error": str(e),
                "timestamp": int(__import__("time").time() * 1000),
            },
            status=500,
        )


@health_router.route("/metrics", methods=["GET"])
async def prometheus_metrics(request):
    """
    Prometheus 格式的监控指标

    返回 Prometheus 文本格式的指标数据
    """
    try:
        stats = await get_collection_application().stats()
        is_healthy = 1 if stats.get("healthy") else 0
        submissions = stats.get("submissions", {})
        rejected = int(submissions.get("busy", 0)) + int(submissions.get("conflict", 0))

        # 生成 Prometheus 格式
        prometheus_text = f"""# HELP stargazer_collection_runtime_healthy Collection runtime health status
# TYPE stargazer_collection_runtime_healthy gauge
stargazer_collection_runtime_healthy {is_healthy}

# HELP stargazer_collection_active_runs Active collection runs in this pod
# TYPE stargazer_collection_active_runs gauge
stargazer_collection_active_runs {stats.get("active_runs", 0)}

# HELP stargazer_collection_active_targets Active target collections in this pod
# TYPE stargazer_collection_active_targets gauge
stargazer_collection_active_targets {stats.get("active_targets", 0)}

# HELP stargazer_collection_target_worker_tasks Created target worker tasks in this pod
# TYPE stargazer_collection_target_worker_tasks gauge
stargazer_collection_target_worker_tasks {stats.get("target_worker_tasks", 0)}

# HELP stargazer_event_loop_lag_seconds Latest event loop scheduling lag
# TYPE stargazer_event_loop_lag_seconds gauge
stargazer_event_loop_lag_seconds {stats.get("event_loop_lag_seconds", 0)}

# HELP stargazer_event_loop_lag_p99_seconds Rolling p99 event loop scheduling lag
# TYPE stargazer_event_loop_lag_p99_seconds gauge
stargazer_event_loop_lag_p99_seconds {stats.get("event_loop_lag_p99_seconds", 0)}

# HELP stargazer_process_threads Active process thread count
# TYPE stargazer_process_threads gauge
stargazer_process_threads {stats.get("thread_count", 0)}

# HELP stargazer_process_open_file_descriptors Open process file descriptors
# TYPE stargazer_process_open_file_descriptors gauge
stargazer_process_open_file_descriptors {stats.get("open_file_descriptors", -1)}

# HELP stargazer_collection_max_active_runs Configured active run limit
# TYPE stargazer_collection_max_active_runs gauge
stargazer_collection_max_active_runs {stats.get("max_active_runs", 0)}

# HELP stargazer_collection_max_active_targets Configured pod target concurrency limit
# TYPE stargazer_collection_max_active_targets gauge
stargazer_collection_max_active_targets {stats.get("max_active_targets", 0)}

# HELP stargazer_collection_submission_rejected_total Rejected collection submissions
# TYPE stargazer_collection_submission_rejected_total counter
stargazer_collection_submission_rejected_total {rejected}

# TYPE stargazer_collection_preflight_duration_seconds_total counter
stargazer_collection_preflight_duration_seconds_total {stats.get("preflight_duration_seconds_total", 0)}
# TYPE stargazer_collection_preflight_total counter
stargazer_collection_preflight_total {stats.get("preflight_total", 0)}
# TYPE stargazer_collection_target_unreachable_total counter
stargazer_collection_target_unreachable_total {stats.get("target_unreachable_total", 0)}
# TYPE stargazer_collection_credential_attempt_total counter
stargazer_collection_credential_attempt_total {stats.get("credential_attempt_total", 0)}
# TYPE stargazer_collection_credential_cooldown_total counter
stargazer_collection_credential_cooldown_total {stats.get("credential_cooldown_total", 0)}
# TYPE stargazer_collection_plugin_duration_seconds_total counter
stargazer_collection_plugin_duration_seconds_total {stats.get("plugin_duration_seconds_total", 0)}
# TYPE stargazer_collection_plugin_duration_seconds_p95 gauge
stargazer_collection_plugin_duration_seconds_p95 {stats.get("plugin_duration_seconds_p95", 0)}
# TYPE stargazer_collection_plugin_duration_seconds_p99 gauge
stargazer_collection_plugin_duration_seconds_p99 {stats.get("plugin_duration_seconds_p99", 0)}
# TYPE stargazer_collection_plugin_total counter
stargazer_collection_plugin_total {stats.get("plugin_total", 0)}
# TYPE stargazer_collection_plugin_timeout_total counter
stargazer_collection_plugin_timeout_total {stats.get("plugin_timeout_total", 0)}
# TYPE stargazer_collection_result_publish_failure_total counter
stargazer_collection_result_publish_failure_total {stats.get("result_publish_failure_total", 0)}
# TYPE stargazer_collection_publish_duration_seconds_p95 gauge
stargazer_collection_publish_duration_seconds_p95 {stats.get("publish_duration_seconds_p95", 0)}
# TYPE stargazer_collection_publish_duration_seconds_p99 gauge
stargazer_collection_publish_duration_seconds_p99 {stats.get("publish_duration_seconds_p99", 0)}
# TYPE stargazer_collection_publish_enqueue_duration_seconds_p95 gauge
stargazer_collection_publish_enqueue_duration_seconds_p95 {stats.get("publish_enqueue_duration_seconds_p95", 0)}
# TYPE stargazer_collection_publish_enqueue_duration_seconds_p99 gauge
stargazer_collection_publish_enqueue_duration_seconds_p99 {stats.get("publish_enqueue_duration_seconds_p99", 0)}
# TYPE stargazer_collection_target_execution_error_total counter
stargazer_collection_target_execution_error_total {stats.get("target_execution_error_total", 0)}
# TYPE stargazer_collection_lease_takeover_total counter
stargazer_collection_lease_takeover_total {stats.get("lease_takeover_total", 0)}
# TYPE stargazer_redis_pool_wait_seconds_total counter
stargazer_redis_pool_wait_seconds_total {stats.get("redis_pool_wait_seconds_total", 0)}
# TYPE stargazer_redis_pool_timeout_total counter
stargazer_redis_pool_timeout_total {stats.get("redis_pool_timeout_total", 0)}
# TYPE stargazer_redis_pool_exhaustion_total counter
stargazer_redis_pool_exhaustion_total {stats.get("redis_pool_exhaustion_total", 0)}
# TYPE stargazer_collection_credential_state_redis_error_total counter
stargazer_collection_credential_state_redis_error_total {stats.get("credential_state_redis_error_total", 0)}
"""
        bounded_metric_keys = (
            "target_worker_tasks_peak",
            "pending_targets",
            "pending_runs",
            "sync_calls_in_flight",
            "target_task_window",
            "publish_queue_depth",
            "publish_queue_peak",
            "publish_queue_capacity",
            "publish_queue_wait_seconds_p95",
            "publish_queue_wait_seconds_p99",
            "publish_queue_residence_seconds_p95",
            "publish_queue_residence_seconds_p99",
            "publish_batch_age_ms",
            "publish_batch_total",
            "publish_batch_items_total",
            "publish_batch_size_p95",
            "publish_batch_size_p99",
            "publish_flush_duration_seconds_p95",
            "publish_flush_duration_seconds_p99",
            "publish_shutdown_timeout_total",
            "result_publish_retry_total",
            "preflight_timeout_total",
            "probe_timeout_total",
            "collection_timeout_total",
            "publish_timeout_total",
            "publish_queue_timeout_total",
            "publish_delivery_timeout_total",
            "publish_connect_failure_total",
            "publish_flush_failure_total",
            "publish_lines_total",
            "publish_bytes_total",
            "publish_succeeded_total",
            "publish_failed_total",
            "publish_unknown_total",
            "publish_confirmed_total",
            "publish_retryable_failed_total",
            "publish_delivery_unknown_total",
            "publish_event_failed_total",
            "publish_permanent_failed_total",
            "publish_chunk_lines_p95",
            "publish_chunk_lines_p99",
            "publish_chunk_bytes_p95",
            "publish_chunk_bytes_p99",
            "publish_targets_per_chunk_p95",
            "publish_targets_per_chunk_p99",
            "publish_encode_duration_seconds_p95",
            "publish_encode_duration_seconds_p99",
            "target_slots_used",
            "target_slots_capacity",
            "target_slots_available",
            "target_slots_utilization_percent",
            "nats_metrics_connected",
            "nats_metrics_reconnecting",
            "nats_metrics_reconnect_total",
            "nats_metrics_reconnect_duration_seconds",
            "nats_metrics_reconnect_duration_seconds_p99",
            "nats_metrics_pending_bytes",
            "nats_js_publish_pending_messages",
            "nats_js_publish_pending_bytes",
            "nats_js_publish_pending_messages_peak",
            "nats_js_publish_pending_bytes_peak",
            "nats_js_publish_confirmed_total",
            "nats_js_puback_duration_seconds_p95",
            "nats_js_puback_duration_seconds_p99",
            "nats_js_puback_timeout_total",
            "nats_js_publish_retry_total",
            "nats_js_publish_rejected_total",
            "run_first_schedule_wait_seconds_p95",
            "run_first_schedule_wait_seconds_p99",
            "job_node_info_lookup_total",
            "job_node_info_lookup_rpc_total",
            "job_node_info_lookup_target_total",
            "job_node_info_lookup_found_total",
            "job_node_info_lookup_missing_total",
            "job_node_info_lookup_ambiguous_total",
            "job_node_info_lookup_failure_total",
            "job_node_info_lookup_duration_seconds_p95",
            "job_node_info_lookup_duration_seconds_p99",
        )
        for key in bounded_metric_keys:
            prometheus_text += f"# TYPE stargazer_collection_{key} gauge\n" f"stargazer_collection_{key} {stats.get(key, 0)}\n"
        for dimension, values in (
            ("execution_mode", ("sync", "async", "remote")),
            ("capacity_group", ("snmp", "sync_sdk", "remote_job", "default")),
        ):
            for suffix in (
                "total",
                "success_total",
                "failed_total",
                "unreachable_total",
                "deferred_total",
                "timeout_total",
                "duration_seconds_p95",
                "duration_seconds_p99",
            ):
                metric_name = f"stargazer_collection_{dimension}_{suffix}"
                metric_type = "counter" if suffix.endswith("total") else "gauge"
                prometheus_text += f"# TYPE {metric_name} {metric_type}\n"
                for value in values:
                    key = f"{dimension}_{value}_{suffix}"
                    prometheus_text += f'{metric_name}{{{dimension}="{value}"}} ' f"{stats.get(key, 0)}\n"

        return response.text(prometheus_text, content_type="text/plain; version=0.0.4")

    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return response.text(f"# Error: {str(e)}", status=500)
