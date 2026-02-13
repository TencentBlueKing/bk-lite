# -- coding: utf-8 --
"""
ARQ Worker 配置和任务处理

负责：
1. 任务入口函数的定义和分发
2. Worker 配置（Redis、并发数、超时等）
3. 任务完成后的清理工作（清除运行标记）
"""

import os
import time
from typing import Dict, Any
from arq import create_pool
from arq.connections import RedisSettings
from core.redis_config import REDIS_CONFIG
from sanic.log import logger


async def collect_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    """
    统一的任务入口函数

    Args:
        ctx: ARQ 上下文
        params: 采集参数
        task_id: 任务ID（业务层生成，用于去重）

    Returns:
        任务执行结果

    Note:
        任务完成后会自动清除运行标记，允许相同参数的任务再次入队
    """
    monitor_type = params.get("monitor_type")
    model_id = params.get("model_id")

    logger.info("=" * 60)
    logger.info(f"Task received: {task_id}")
    logger.info(f"Type: {monitor_type or model_id}")
    logger.info(f"Host: {params.get('host', 'N/A')}")
    logger.info("=" * 60)

    result = None
    try:
        # 根据任务类型分发到对应的 handler
        if monitor_type == "vmware":
            from tasks.handlers.monitor_handler import collect_vmware_metrics_task

            result = await collect_vmware_metrics_task(ctx, params, task_id)

        elif monitor_type == "qcloud":
            from tasks.handlers.monitor_handler import collect_qcloud_metrics_task

            result = await collect_qcloud_metrics_task(ctx, params, task_id)

        elif monitor_type == "sangforscp":
            try:
                from enterprise.tasks.handlers.sangforscp_handler import (
                    collect_sangforscp_metrics_task,
                )

                result = await collect_sangforscp_metrics_task(ctx, params, task_id)
            except ImportError:
                logger.error(f"Enterprise module not available for task {task_id}")
                result = {
                    "task_id": task_id,
                    "status": "failed",
                    "error": "Enterprise module not available",
                    "completed_at": int(time.time() * 1000),
                }

        elif monitor_type == "test":
            # 测试任务 - 用于验证 Worker 是否正常工作
            logger.info(f"Test task completed: {params.get('message', 'No message')}")
            result = {
                "task_id": task_id,
                "status": "success",
                "message": "Test task executed successfully",
                "params": params,
                "completed_at": int(time.time() * 1000),
            }

        elif model_id:
            from tasks.handlers.plugin_handler import collect_plugin_task

            result = await collect_plugin_task(ctx, params, task_id)

        else:
            logger.error(f"Unknown task type for {task_id}")
            result = {
                "task_id": task_id,
                "status": "failed",
                "error": "Unknown task type",
                "completed_at": int(time.time() * 1000),
            }

        return result

    finally:
        # 清除运行标记，允许相同参数的任务再次入队
        await _clear_running_flag(task_id)


async def _clear_running_flag(task_id: str):
    """
    清除任务运行标记

    这是一个独立的辅助函数，确保无论任务成功或失败都会执行
    """
    try:
        redis_settings = RedisSettings(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            password=REDIS_CONFIG["password"],
            database=REDIS_CONFIG["database"],
        )

        pool = await create_pool(redis_settings)
        running_key = f"task:running:{task_id}"
        await pool.delete(running_key)
        await pool.aclose()

        logger.info(f"Task {task_id} completed, cleared running flag")

    except Exception as e:
        logger.warning(f"Failed to clear running flag for {task_id}: {e}")


class WorkerSettings:
    """
    ARQ Worker 配置

    配置项说明：
    - redis_settings: Redis 连接配置
    - functions: 注册的任务函数列表
    - max_jobs: 最大并发任务数
    - job_timeout: 单个任务超时时间（秒）
    - keep_result: 任务结果保留时间（秒）
    - max_tries: 任务失败重试次数
    """

    # Redis 连接配置（使用统一的配置源）
    redis_settings = RedisSettings(
        host=REDIS_CONFIG["host"],
        port=REDIS_CONFIG["port"],
        password=REDIS_CONFIG["password"],
        database=REDIS_CONFIG["database"],
    )

    # 注册的任务函数
    functions = [collect_task]

    # Worker 运行配置
    max_jobs = int(os.getenv("TASK_MAX_JOBS", "10"))
    job_timeout = int(os.getenv("TASK_JOB_TIMEOUT", "300"))
    keep_result = int(os.getenv("TASK_KEEP_RESULT", "3600"))
    max_tries = int(os.getenv("TASK_MAX_TRIES", "3"))
