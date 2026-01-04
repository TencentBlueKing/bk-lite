# -- coding: utf-8 --
# @File: plugin_handler.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
插件采集任务处理器
处理各种插件（MySQL、Redis、Nginx等）的数据采集任务
"""
import time
import traceback
from typing import Dict, Any
from sanic.log import logger


async def collect_plugin_task(ctx: Dict, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """
    插件采集任务处理器

    Args:
        ctx: ARQ 上下文
        params: 采集参数，包含 plugin_name 等
        task_id: 任务ID

    Returns:
        任务执行结果
    """
    plugin_name = params.get('plugin_name')
    logger.info(f"[Plugin Task] Processing: {task_id}, plugin: {plugin_name}")

    try:
        # 导入服务和工具（延迟导入避免循环依赖）
        from service.collection_service import CollectionService
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_plugin_error_metrics

        # 执行采集
        collect_service = CollectionService(params)
        metrics_data = await collect_service.collect()

        logger.info(f"[Plugin Task] {task_id} completed successfully")

        # 推送到 NATS
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "plugin_name": plugin_name,
            "completed_at": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"[Plugin Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}")

        # 导入工具函数
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_plugin_error_metrics

        # 生成错误指标
        error_metrics = generate_plugin_error_metrics(params, e)

        # 推送错误指标到 NATS
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "plugin_name": plugin_name,
            "completed_at": int(time.time() * 1000)
        }

