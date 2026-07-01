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


def _should_publish_monitor_error_metrics(error: Exception) -> bool:
    from tasks.utils.nats_helper import MetricsPublishError

    return not (
        isinstance(error, MetricsPublishError)
        and (
            getattr(error, "success_count", 0) > 0
            or getattr(error, "delivery_detected", False)
        )
    )


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

        if _should_publish_monitor_error_metrics(e):
            error_metrics = generate_monitor_error_metrics(params, e)
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

        if _should_publish_monitor_error_metrics(e):
            error_metrics = generate_monitor_error_metrics(params, e)
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

        if _should_publish_monitor_error_metrics(e):
            error_metrics = generate_monitor_error_metrics(params, e)
            await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "oceanstor",
            "completed_at": int(time.time() * 1000),
        }


async def _collect_storage_metrics_task(
    ctx: Dict,
    params: Dict[str, Any],
    task_id: str,
    monitor_type: str,
    collector_path: str,
    collector_name: str,
) -> Dict[str, Any]:
    logger.info("[%s Task] Processing: %s", monitor_type, task_id)

    try:
        from tasks.utils.nats_helper import publish_metrics_to_nats

        module_name, class_name = collector_path.rsplit(".", 1)
        module = __import__(module_name, fromlist=[class_name])
        collector_cls = getattr(module, class_name)
        collector = collector_cls(params)
        metrics_data = await collector.collect()

        logger.info(
            "[%s Task] %s completed, data size: %s bytes",
            collector_name,
            task_id,
            len(metrics_data),
        )

        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": monitor_type,
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            "[%s Task] %s failed: %s\n%s",
            collector_name,
            task_id,
            str(e),
            traceback.format_exc(),
        )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        if _should_publish_monitor_error_metrics(e):
            error_metrics = generate_monitor_error_metrics(params, e)
            await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": monitor_type,
            "completed_at": int(time.time() * 1000),
        }


async def collect_pure_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    return await _collect_storage_metrics_task(
        ctx,
        params,
        task_id,
        "pure",
        "tasks.collectors.pure_collector.PureCollector",
        "Pure",
    )


async def collect_infinibox_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    return await _collect_storage_metrics_task(
        ctx,
        params,
        task_id,
        "infinibox",
        "tasks.collectors.infinibox_collector.InfiniBoxCollector",
        "InfiniBox",
    )


async def collect_host_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    logger.info(f"[Host Task] Processing: {task_id}")
    callback_context_stored = False
    remote_submission_accepted = False

    try:
        from tasks.collectors.host_collector import HostCollector

        collector = HostCollector(params)
        callback_task_id = str(task_id)
        callback_timestamp = int(time.time() * 1000)
        callback_subject = host_remote_callback.get_host_remote_callback_subject()
        callback_payload = {
            "collect_task_id": callback_task_id,
            "instance_id": params.get("tags", {}).get("instance_id", params.get("host")),
            "instance_name": params.get("host"),
            "model_id": params.get("model_id", params.get("monitor_type", "host")),
        }
        callback_params = _build_host_remote_callback_params(params)
        callback_params["callback_timestamp"] = callback_timestamp

        await host_remote_callback.store_host_remote_callback_context(
            callback_task_id,
            callback_params,
            ctx,
        )
        callback_context_stored = True
        host_remote_callback.log_host_remote_event(
            "submit_received",
            callback_task_id,
            monitor_type="host",
            host=params.get("host"),
        )

        logger.info(f"[Host Task] Submitting remote collection: {task_id}")
        accepted = await collector.submit_collection(
            callback_task_id,
            callback_subject,
            callback_payload,
        )
        accepted_result = accepted.get("result") or {}
        if accepted.get("success") is False or accepted_result.get("accepted") is False:
            raise RuntimeError(
                accepted.get("error")
                or accepted_result.get("error")
                or "Host Remote submission failed"
            )
        accepted_task_id = str(accepted_result.get("task_id") or callback_task_id).strip()
        if accepted_task_id != callback_task_id:
            raise RuntimeError(
                f"Host Remote submission task_id mismatch: expected {callback_task_id}, got {accepted_task_id}"
            )

        remote_submission_accepted = True
        await host_remote_callback.mark_host_remote_submit_accepted(callback_task_id)
        host_remote_callback.log_host_remote_event(
            "submit_accepted",
            callback_task_id,
            monitor_type="host",
            host=params.get("host"),
            accepted_task_id=accepted_task_id,
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
            "defer_running_clear": True,
            "submitted_at": callback_timestamp,
        }

    except Exception as e:
        logger.error(
            f"[Host Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        if callback_context_stored and not remote_submission_accepted:
            try:
                await host_remote_callback.clear_host_remote_callback_context(task_id)
            except Exception as cleanup_err:
                logger.error(
                    f"[Host Task] Failed to clear callback context for {task_id}: {cleanup_err}",
                    exc_info=True,
                )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        error_metrics = generate_monitor_error_metrics(params, e)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)
        host_remote_callback.log_host_remote_event(
            "submit_failed",
            task_id,
            level="error",
            monitor_type="host",
            host=params.get("host"),
            error=str(e),
        )

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "host",
            "completed_at": int(time.time() * 1000),
        }


async def collect_windows_wmi_metrics_task(
    ctx: Dict, params: Dict[str, Any], task_id: str
) -> Dict[str, Any]:
    logger.info(f"[Windows WMI Task] Processing: {task_id}")

    try:
        from tasks.collectors.host_wmi_collector import WindowsWmiCollector
        from tasks.utils.nats_helper import publish_metrics_to_nats

        collector = WindowsWmiCollector(params)
        metrics_data = await collector.collect()
        await publish_metrics_to_nats(ctx, metrics_data, params, task_id)

        return {
            "task_id": task_id,
            "status": "success",
            "monitor_type": "windows_wmi",
            "data_size": len(metrics_data),
            "completed_at": int(time.time() * 1000),
        }

    except Exception as e:
        logger.error(
            f"[Windows WMI Task] {task_id} failed: {str(e)}\n{traceback.format_exc()}"
        )

        from tasks.utils.nats_helper import publish_metrics_to_nats
        from tasks.utils.metrics_helper import generate_monitor_error_metrics

        error_metrics = generate_monitor_error_metrics(params, e)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)

        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
            "monitor_type": "windows_wmi",
            "completed_at": int(time.time() * 1000),
        }
