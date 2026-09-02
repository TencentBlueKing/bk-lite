import inspect
from datetime import datetime, timezone

import core.collection.host_remote.callback as host_remote_callback
from core.collection.host_remote.runtime import schedule_host_remote_processing
from core.collection.round_metadata import ROUND_METADATA_SCHEMA_VERSION, RedisRoundMetadataStore, RoundMetadataValidationError, validate_lookups
from core.infra.nats import get_nats, register_handler
from core.infra.redis_client import get_redis_client
from sanic.log import logger
from service.collection_service import CollectionService
from service.debug.protocol_debug_service import ProtocolDebugService


def _handler_queue(handler_name: str) -> str:
    """队列组名沿用完整 subject，与 host_remote.callback 的既有惯例一致。

    多 Sanic worker 下每个 worker 进程都会执行 before_server_start 并各订阅一次；
    NATS 对没有队列组的订阅是广播语义，同一请求会被每个 worker 重复执行一遍
    （debug_snmp / debug_ipmi 会因此对目标设备重复探测），而发起方只取第一个响应。
    """
    return f"{host_remote_callback.get_stargazer_service_name()}.{handler_name}"


async def _round_metadata_store():
    return RedisRoundMetadataStore(await get_redis_client())


@register_handler(
    "get_collection_round_metadata",
    queue="stargazer-round-metadata",
)
async def get_collection_round_metadata(data):
    """按完整轮次键精确读取快照控制元数据，不提供扫描能力。"""
    if not isinstance(data, dict):
        raise RoundMetadataValidationError("invalid_request")
    if data.get("schema_version") != ROUND_METADATA_SCHEMA_VERSION:
        raise RoundMetadataValidationError("invalid_request")
    task_id = str(data.get("collection_task_id") or "").strip()
    instance_id = str(data.get("instance_id") or "").strip()
    if not task_id or instance_id != f"cmdb_{task_id}":
        raise RoundMetadataValidationError("invalid_request")
    lookups = validate_lookups(data.get("lookups"))
    store = _round_metadata_store()
    if inspect.isawaitable(store):
        store = await store
    items = await store.get_many(task_id, lookups)
    return {"schema_version": ROUND_METADATA_SCHEMA_VERSION, "items": items}


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


@register_handler("list_regions", queue=_handler_queue("list_regions"))
async def list_regions(data):
    """处理 list_regions 请求"""
    logger.debug(f"list_regions received: {data}")
    collect_service = CollectionService(data)
    regions = await collect_service.list_regions()
    return {"regions": regions}


@register_handler("test_connection", queue=_handler_queue("test_connection"))
async def test_connection(data):
    """测试连接"""
    logger.info(f"test_connection received: {data}")
    return {"result": True, "data": data}


@register_handler("health_check", queue=_handler_queue("health_check"))
async def health_check(data):
    return {
        "status": "ok",
        "instance_id": get_nats().service_name,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@register_handler("debug_snmp", queue=_handler_queue("debug_snmp"))
async def debug_snmp(data: dict) -> dict:
    """
    接收 CMDB 的 SNMP 诊断请求。
    data 字段：protocol, action, target, port, timeout, credential, oid(可选，仅 get_oid)
    返回：success, stage, summary, raw_log, duration_ms
    """
    logger.info(f"debug_snmp received: action={data.get('action')} target={data.get('target')}")
    return await ProtocolDebugService(data).execute()


@register_handler("debug_ipmi", queue=_handler_queue("debug_ipmi"))
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

    host_remote_callback.validate_host_remote_callback_identity(payload, callback_context)
    await host_remote_callback.ensure_host_remote_callback_fence_is_current(callback_context)

    claim_token = await host_remote_callback.claim_host_remote_processing(task_id)
    if not claim_token:
        return {
            "task_id": task_id,
            "status": "duplicate_active",
            "monitor_type": (callback_context.get("params") or {}).get("monitor_type", "host"),
            "processing_job_id": "",
        }

    try:
        callback_context = await host_remote_callback.record_host_remote_callback_payload(
            task_id,
            payload,
        )
        if callback_context is None:
            raise RuntimeError("Host Remote callback context disappeared before record")
        await _clear_host_remote_running_flag_best_effort(task_id)
        task_info = await schedule_host_remote_processing(task_id, claim_token=claim_token)
    except Exception:
        await host_remote_callback.release_host_remote_processing_claim(task_id, claim_token)
        raise
    await host_remote_callback.mark_host_remote_processing_enqueued(
        task_id,
        processing_job_id=task_info.get("processing_id"),
    )
    host_remote_callback.log_host_remote_event(
        "callback_processing_queued",
        task_id,
        processing_job_id=task_info.get("processing_id"),
    )

    return {
        "task_id": task_id,
        "status": "accepted",
        "monitor_type": (callback_context.get("params") or {}).get("monitor_type", "host"),
        "processing_job_id": task_info.get("processing_id", ""),
    }
