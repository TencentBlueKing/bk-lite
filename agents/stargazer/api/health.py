# -- coding: utf-8 --
# @File: health.py
# @Time: 2025/12/20
# @Author: AI Assistant
"""
健康检查和监控 API
提供统一采集运行时健康状态与容量监控信息
"""
from sanic import Blueprint, response
from sanic.log import logger
from core.collection.application import get_collection_application

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
    return response.json({
        "status": "ok",
        "timestamp": int(__import__("time").time() * 1000)
    })


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

    return response.json({
        "ready": all_ready,
        "checks": checks,
        "timestamp": int(__import__("time").time() * 1000)
    }, status=status_code)


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
        return response.json({
            "healthy": False,
            "error": str(e),
            "timestamp": int(__import__("time").time() * 1000)
        }, status=500)


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
        rejected = int(submissions.get("busy", 0)) + int(
            submissions.get("conflict", 0)
        )

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
# TYPE stargazer_collection_plugin_total counter
stargazer_collection_plugin_total {stats.get("plugin_total", 0)}
# TYPE stargazer_collection_plugin_timeout_total counter
stargazer_collection_plugin_timeout_total {stats.get("plugin_timeout_total", 0)}
# TYPE stargazer_collection_result_publish_failure_total counter
stargazer_collection_result_publish_failure_total {stats.get("result_publish_failure_total", 0)}
# TYPE stargazer_collection_lease_takeover_total counter
stargazer_collection_lease_takeover_total {stats.get("lease_takeover_total", 0)}
"""

        return response.text(prometheus_text, content_type="text/plain; version=0.0.4")

    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return response.text(f"# Error: {str(e)}", status=500)
