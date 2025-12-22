# -- coding: utf-8 --
# @File: monitor_handler.py
# @Time: 2025/12/19
# @Author: AI Assistant
"""
监控指标采集任务处理器
处理 VMware、QCloud 等监控平台的指标采集任务
"""
import time
import traceback
from typing import Dict, Any
from sanic.log import logger


async def collect_vmware_metrics_task(ctx: Dict, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """
    VMware 监控指标采集任务处理器

    Args:
        ctx: ARQ 上下文
        params: 采集参数，包含 username, password, host, minutes
        task_id: 任务ID

    Returns:
        任务执行结果
    """
    logger.info(f"[VMware Task] Processing: {task_id}")

    try:
        from tasks.collectors.vmware_collector import VmwareCollector
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        # 执行采集
        collector = VmwareCollector(params)
        metrics_data = await collector.collect()

        logger.info(f"[VMware Task] {task_id} completed, data size: {len(metrics_data)} bytes")

        # 推送到 NATS
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "vmware",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"[VMware Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}")

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        # 生成错误指标
        error_metrics = generate_monitor_error_metrics(params, e)

        # 推送错误指标到 NATS
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "vmware",
            "completed_at": int(time.time() * 1000)
        }


async def collect_qcloud_metrics_task(ctx: Dict, params: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """
    QCloud 监控指标采集任务处理器

    Args:
        ctx: ARQ 上下文
        params: 采集参数，包含 username, password, minutes
        task_id: 任务ID

    Returns:
        任务执行结果
    """
    logger.info(f"[QCloud Task] Processing: {task_id}")

    try:
        from tasks.collectors.qcloud_collector import QCloudCollector
        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        # 执行采集
        collector = QCloudCollector(params)
        metrics_data = await collector.collect()

        logger.info(f"[QCloud Task] {task_id} completed, data size: {len(metrics_data)} bytes")

        # 推送到 NATS
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "qcloud",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000)
        }

    except Exception as e:
        logger.error(f"[QCloud Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}")

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        # 生成错误指标
        error_metrics = generate_monitor_error_metrics(params, e)

        # 推送错误指标到 NATS
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "qcloud",
            "completed_at": int(time.time() * 1000)
        }

