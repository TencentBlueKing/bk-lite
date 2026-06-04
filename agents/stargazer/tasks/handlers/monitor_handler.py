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

import core.host_remote_callback as host_remote_callback


def _build_host_remote_callback_params(params: Dict[str, Any]) -> Dict[str, Any]:
    callback_params = {}
    for key in ("host", "os_type", "monitor_type"):
        value = params.get(key)
        if value is not None:
            callback_params[key] = value

    tags = params.get("tags")
    if isinstance(tags, dict):
        callback_params["tags"] = dict(tags)

    return callback_params


async def collect_vmware_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
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

        logger.info(
            f"[VMware Task] {task_id} completed, data size: {len(metrics_data)} bytes"
        )

        # 推送到 NATS
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "vmware_vc",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[VMware Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

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
            "monitor_type": "vmware_vc",
            "completed_at": int(time.time() * 1000),
        }


async def collect_qcloud_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
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

        logger.info(
            f"[QCloud Task] {task_id} completed, data size: {len(metrics_data)} bytes"
        )

        # 推送到 NATS
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "qcloud",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[QCloud Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

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
            "completed_at": int(time.time() * 1000),
        }


async def collect_oceanstor_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    logger.info(f"[OceanStor Task] Processing: {task_id}")

    try:
        from tasks.collectors.oceanstor_collector import OceanStorCollector
        from tasks.utils.nats_helper import publish_metrics_to_nats

        collector = OceanStorCollector(params)
        metrics_data = await collector.collect()

        logger.info(
            f"[OceanStor Task] {task_id} completed, data size: {len(metrics_data)} bytes"
        )

        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "oceanstor",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[OceanStor Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        error_metrics = generate_monitor_error_metrics(params, e)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "oceanstor",
            "completed_at": int(time.time() * 1000),
        }


async def collect_host_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    logger.info(f"[Host Task] Processing: {task_id}")

    try:
        from tasks.collectors.host_collector import HostCollector

        collector = HostCollector(params)
        callback_subject = host_remote_callback.get_host_remote_callback_subject()
        callback_payload = {
            "collect_task_id": task_id,
            "instance_id": params.get("tags", {}).get("instance_id", params.get("host")),
            "instance_name": params.get("host"),
            "model_id": params.get("model_id", params.get("monitor_type", "host")),
        }

        logger.info(f"[Host Task] Submitting remote collection: {task_id}")
        accepted = await collector.submit_collection(callback_subject, callback_payload)
        accepted_result = accepted.get("result") or {}
        if accepted.get("success") is False or accepted_result.get("accepted") is False:
            raise RuntimeError(
                accepted.get("error")
                or accepted_result.get("error")
                or "Host Remote submission failed"
            )
        accepted_task_id = str(accepted_result.get("task_id") or "").strip()
        if not accepted_task_id:
            raise RuntimeError("Host Remote submission missing accepted task_id")

        await host_remote_callback.store_host_remote_callback_context(
            accepted_task_id, _build_host_remote_callback_params(params), ctx
        )
        logger.info(
            f"[Host Task] Remote collection accepted: collect_task_id={task_id}, "
            f"accepted_task_id={accepted_task_id}"
        )

        return {
            "task_id": task_id,
            "status": accepted_result.get("status", "queued"),
            "monitor_type": "host",
            "accepted": accepted_result.get("accepted", True),
            "accepted_task_id": accepted_task_id,
            "submitted_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[Host Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        error_metrics = generate_monitor_error_metrics(params, e)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "host",
            "completed_at": int(time.time() * 1000),
        }
