# -- coding: utf-8 --
# @File: nats_server.py
# @Time: 2025/4/25 17:04
# @Author: windyzhao
from sanic.log import logger
from service.collect_service import CollectService
from core.nats import register_handler


@register_handler("list_regions")
async def list_regions(data):
    """处理 list_regions 请求"""
    logger.info(f"list_regions received: {data}")
    kwargs = data.get("kwargs", {})
    collect_service = CollectService(kwargs)
    regions = collect_service.list_regions()
    return {"regions": regions}


@register_handler("test_connection")
async def test_connection(data):
    """测试连接"""
    logger.info(f"test_connection received: {data}")
    return {"result": True, "data": data}
