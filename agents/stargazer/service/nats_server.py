# -- coding: utf-8 --
# @File: nats_server.py
# @Time: 2025/4/25 17:04
# @Author: windyzhao
from datetime import datetime, timezone

from sanic.log import logger
from service.collection_service import CollectionService
from core.nats import register_handler, get_nats


@register_handler("list_regions")
async def list_regions(data):
    """处理 list_regions 请求"""
    logger.info(f"list_regions received: {data}")
    kwargs = data.get("kwargs", {})
    collect_service = CollectionService(kwargs)
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
