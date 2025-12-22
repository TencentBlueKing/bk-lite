# -- coding: utf-8 --
# @File: worker.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
ARQ Worker 配置
负责任务调度和分发，具体任务逻辑在 tasks 目录中
"""
import os
import time
from typing import Dict, Any
from arq.connections import RedisSettings
from sanic.log import logger as sanic_logger
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 使用简单的日志记录器
class SimpleLogger:
    def info(self, msg):
        print(f"[INFO] {msg}")

    def error(self, msg):
        print(f"[ERROR] {msg}")

    def warning(self, msg):
        print(f"[WARNING] {msg}")

try:
    logger = sanic_logger
except:
    logger = SimpleLogger()


async def collect_task(ctx: Dict, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """
    统一的任务入口函数
    根据任务类型分发到不同的任务处理器

    Args:
        ctx: ARQ 上下文
        params: 采集参数
        task_id: 任务ID

    Returns:
        任务执行结果
    """
    monitor_type = params.get("monitor_type")
    plugin_name = params.get("plugin_name")

    logger.info(f"[Worker] Task received: {task_id}, type: {monitor_type or plugin_name}")

    # 判断任务类型并分发到对应的 handler
    if monitor_type == "vmware":
        from tasks.handlers.monitor_handler import collect_vmware_metrics_task
        return await collect_vmware_metrics_task(ctx, params, task_id)

    elif monitor_type == "qcloud":
        from tasks.handlers.monitor_handler import collect_qcloud_metrics_task
        return await collect_qcloud_metrics_task(ctx, params, task_id)

    elif plugin_name:
        from tasks.handlers.plugin_handler import collect_plugin_task
        return await collect_plugin_task(ctx, params, task_id)

    else:
        logger.error(f"[Worker] Unknown task type for {task_id}")
        return {
            "task_id": task_id,
            "status": "failed",
            "error": "Unknown task type",
            "completed_at": int(time.time() * 1000)
        }


async def startup(ctx: Dict):
    """Worker 启动时执行"""
    logger.info("=" * 60)
    logger.info("ARQ Worker started successfully")
    logger.info("Task handlers loaded from 'tasks/handlers/'")
    logger.info("=" * 60)
    ctx['start_time'] = time.time()


async def shutdown(ctx: Dict):
    """Worker 关闭时执行"""
    uptime = int(time.time() - ctx.get('start_time', time.time()))
    logger.info("=" * 60)
    logger.info(f"ARQ Worker shutting down (uptime: {uptime}s)")
    logger.info("=" * 60)


class WorkerSettings:
    """ARQ Worker 配置"""

    # Redis 连接配置
    redis_settings = RedisSettings(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD"),
        database=int(os.getenv("REDIS_DB", "0")),
    )

    # 任务函数列表
    functions = [collect_task]

    # 启动和关闭钩子
    on_startup = startup
    on_shutdown = shutdown

    # Worker 配置
    max_jobs = int(os.getenv("TASK_MAX_JOBS", "10"))
    job_timeout = int(os.getenv("TASK_JOB_TIMEOUT", "300"))
    keep_result = int(os.getenv("TASK_KEEP_RESULT", "3600"))

    # 任务重试配置
    max_tries = int(os.getenv("TASK_MAX_TRIES", "3"))
