from datetime import datetime, timezone

import core.host_remote_callback as host_remote_callback
from core.nats import get_nats, register_handler
from core.task_queue import get_task_queue
from sanic.log import logger
from service.collection_service import CollectionService
from service.debug.protocol_debug_service import ProtocolDebugService
from plugins.inputs.ip_discovery.ip_discovery_handler import handle_ip_scan

# 注册 IP 发现 NATS handler：subject "{stargazer_namespace}.ip_scan"
# 与 server dispatch_ip_discovery 下发的 subject 对应
register_handler("ip_scan")(handle_ip_scan)


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


async def _clear_host_remote_callback_context_best_effort(task_id: str) -> None:
    try:
        await host_remote_callback.clear_host_remote_callback_context(task_id)
    except Exception as err:
        logger.error(
            f"Host Remote callback context cleanup failed for {task_id}: {err}",
            exc_info=True,
        )


async def _clear_host_remote_running_flag_best_effort(task_id: str) -> None:
    try:
        await host_remote_callback.clear_host_remote_running_flag(task_id)
    except Exception as err:
        logger.error(
            f"Host Remote running flag cleanup failed for {task_id}: {err}",
            exc_info=True,
        )


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


@register_handler(
    host_remote_callback.HOST_REMOTE_CALLBACK_HANDLER,
    queue=host_remote_callback.get_host_remote_callback_queue(),
)
async def handle_host_remote_callback(data: dict) -> dict:
    payload = _extract_host_remote_callback_payload(data)
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise RuntimeError("Host Remote callback payload missing task_id")

    callback_context = await host_remote_callback.load_host_remote_callback_context(task_id)
    if not callback_context:
        raise RuntimeError(f"Missing Host Remote callback context for task_id={task_id}")

    if callback_context.get("raw_callback") is None:
        callback_context = await host_remote_callback.record_host_remote_callback_payload(
            task_id,
            payload,
        )

    await _clear_host_remote_running_flag_best_effort(task_id)

    task_queue = get_task_queue()
    task_info = await task_queue.enqueue_host_remote_processing_task(task_id)
    await host_remote_callback.mark_host_remote_processing_enqueued(
        task_id,
        processing_job_id=task_info.get("job_id"),
    )
    host_remote_callback.log_host_remote_event(
        "callback_processing_queued",
        task_id,
        processing_job_id=task_info.get("job_id"),
    )

    return {
        "task_id": task_id,
        "status": "accepted",
        "monitor_type": (callback_context.get("params") or {}).get("monitor_type", "host"),
        "processing_job_id": task_info.get("job_id", ""),
    }
