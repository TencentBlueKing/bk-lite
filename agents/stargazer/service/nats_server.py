from datetime import datetime, timezone

from core.nats import get_nats, register_handler
from sanic.log import logger
from service.collection_service import CollectionService
from service.debug.protocol_debug_service import ProtocolDebugService


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
