# -- coding: utf-8 --
# @File: health.py
# @Time: 2025/12/20
# @Author: AI Assistant
"""
健康检查和监控 API
提供系统健康状态、任务队列统计等监控信息
"""
from sanic import Blueprint, response
from sanic.log import logger
from core.task_queue import get_task_queue

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
            "task_queue": "healthy",
            "redis": "connected"
        }
    }
    """
    checks = {}
    all_ready = True

    # 检查任务队列
    try:
        task_queue = get_task_queue()
        if task_queue._is_healthy:
            checks["task_queue"] = "healthy"
            checks["redis"] = "connected"
        else:
            checks["task_queue"] = "unhealthy"
            checks["redis"] = "disconnected"
            all_ready = False
    except Exception as e:
        checks["task_queue"] = f"error: {str(e)}"
        all_ready = False

    status_code = 200 if all_ready else 503

    return response.json({
        "ready": all_ready,
        "checks": checks,
        "timestamp": int(__import__("time").time() * 1000)
    }, status=status_code)


@health_router.route("/stats", methods=["GET"])
async def queue_stats(request):
    """
    任务队列统计信息

    返回示例：
    {
        "healthy": true,
        "queued_jobs": 5,
        "metrics": {
            "tasks_enqueued": 1234,
            "tasks_skipped": 56,
            "tasks_failed": 12,
            "redis_connection_errors": 2
        },
        "redis_info": {...},
        "timestamp": 1703001234567
    }
    """
    try:
        task_queue = get_task_queue()
        stats = await task_queue.get_queue_stats()
        return response.json(stats)
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
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
        task_queue = get_task_queue()
        stats = await task_queue.get_queue_stats()

        metrics = stats.get("metrics", {})
        queued_jobs = stats.get("queued_jobs", 0)
        is_healthy = 1 if stats.get("healthy") else 0

        # 生成 Prometheus 格式
        prometheus_text = f"""# HELP stargazer_task_queue_healthy Task queue health status (1=healthy, 0=unhealthy)
# TYPE stargazer_task_queue_healthy gauge
stargazer_task_queue_healthy {is_healthy}

# HELP stargazer_task_queue_length Current number of tasks in queue
# TYPE stargazer_task_queue_length gauge
stargazer_task_queue_length {queued_jobs}

# HELP stargazer_tasks_enqueued_total Total number of tasks enqueued
# TYPE stargazer_tasks_enqueued_total counter
stargazer_tasks_enqueued_total {metrics.get("tasks_enqueued", 0)}

# HELP stargazer_tasks_skipped_total Total number of tasks skipped (duplicate)
# TYPE stargazer_tasks_skipped_total counter
stargazer_tasks_skipped_total {metrics.get("tasks_skipped", 0)}

# HELP stargazer_tasks_failed_total Total number of tasks failed
# TYPE stargazer_tasks_failed_total counter
stargazer_tasks_failed_total {metrics.get("tasks_failed", 0)}

# HELP stargazer_redis_connection_errors_total Total number of Redis connection errors
# TYPE stargazer_redis_connection_errors_total counter
stargazer_redis_connection_errors_total {metrics.get("redis_connection_errors", 0)}
"""

        return response.text(prometheus_text, content_type="text/plain; version=0.0.4")

    except Exception as e:
        logger.error(f"Failed to generate Prometheus metrics: {e}")
        return response.text(f"# Error: {str(e)}", status=500)
