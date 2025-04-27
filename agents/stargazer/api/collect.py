# -- coding: utf-8 --
# @File: collect.py
# @Time: 2025/2/27 10:41
# @Author: windyzhao
from sanic import Blueprint
from sanic.log import logger
from sanic import response

from service.collect_service import CollectService

collect_router = Blueprint("collect", url_prefix="/collect")


@collect_router.get("/collect_info")
async def collect(request):
    params = {k.split("_cmdb_", 1)[-1]: v for k, v in dict(request.headers).items() if k.startswith("_cmdb")}
    if not params:
        params = {i[0]: i[1] for i in request.query_args}
    collect_service = CollectService(params)
    metrics_data = collect_service.collect()
    logger.info("Metrics data generated....")
    return response.raw(metrics_data, content_type='text/plain; version=0.0.4; charset=utf-8')
