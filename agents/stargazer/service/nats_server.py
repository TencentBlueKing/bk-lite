# -- coding: utf-8 --
# @File: nats_server.py
# @Time: 2025/4/25 17:04
# @Author: windyzhao
from datetime import datetime, timezone

import core.host_remote_callback as host_remote_callback
from core.nats import get_nats, register_handler
from sanic.log import logger
from service.collection_service import CollectionService
from service.debug.protocol_debug_service import ProtocolDebugService
from tasks.collectors.host_collector import HostCollector
from tasks.utils.metrics_helper import generate_monitor_error_metrics
from tasks.utils.nats_helper import publish_metrics_to_nats


def _extract_host_remote_callback_payload(data):
    if not isinstance(data, dict):
        raise RuntimeError("Host Remote callback payload must be an object")

    args = data.get("args")
    if isinstance(args, list) and args and isinstance(args[0], dict):
        return args[0]

    kwargs = data.get("kwargs")
    if isinstance(kwargs, dict) and isinstance(kwargs.get("data"), dict):
        return kwargs["data"]

    return data


@register_handler("list_regions")
async def list_regions(data):
    """处理 list_regions 请求"""
    logger.debug(f"list_regions received: {data}")
    collect_service = CollectionService(data)
    regions = collect_service.list_regions()
    return {"regions": regions}


@register_handler("test_connection")
async def test_connection(data):
    """测试连接"""
    logger.info(f"test_connection received: {data}")
    return {"result": True, "data": data}


@register_handler("health_check")
async def health_check(data):
    return {
        "status": "ok",
        "instance_id": get_nats().service_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@register_handler("debug_snmp")
async def debug_snmp(data: dict) -> dict:
    """
    接收 CMDB 的 SNMP 诊断请求。
    data 字段：protocol, action, target, port, timeout, credential, oid(可选，仅 get_oid)
    返回：success, stage, summary, raw_log, duration_ms
    """
    logger.info(f"debug_snmp received: action={data.get('action')} target={data.get('target')}")
    return await ProtocolDebugService(data).execute()


@register_handler("debug_ipmi")
async def debug_ipmi(data: dict) -> dict:
    """
    接收 CMDB 的 IPMI 诊断请求。
    data 字段：protocol, action, target, port, timeout, credential
    返回：success, stage, summary, raw_log, duration_ms
    """
    logger.info(f"debug_ipmi received: action={data.get('action')} target={data.get('target')}")
    return await ProtocolDebugService(data).execute()


@register_handler(host_remote_callback.HOST_REMOTE_CALLBACK_HANDLER)
async def handle_host_remote_callback(data: dict) -> dict:
    payload = _extract_host_remote_callback_payload(data)
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("Host Remote callback payload missing task_id")

    callback_context = await host_remote_callback.load_host_remote_callback_context(task_id)
    if not callback_context:
        raise RuntimeError(f"Missing Host Remote callback context for task_id={task_id}")

    params = callback_context["params"]
    ctx = callback_context.get("ctx") or {}

    try:
        collector = HostCollector(params)
        metrics_data = collector.process_adhoc_result(payload)
    except Exception as err:
        logger.error(f"Host Remote callback processing failed for {task_id}: {err}", exc_info=True)
        error_metrics = generate_monitor_error_metrics(params, err)
        await publish_metrics_to_nats(ctx, error_metrics, params, task_id)
        await host_remote_callback.clear_host_remote_callback_context(task_id)
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(err),
            "monitor_type": params.get("monitor_type", "host"),
        }

    await publish_metrics_to_nats(ctx, metrics_data, params, task_id)
    await host_remote_callback.clear_host_remote_callback_context(task_id)
    return {
        "task_id": task_id,
        "status": "success",
        "monitor_type": params.get("monitor_type", "host"),
        "data_size": len(metrics_data),
    }
