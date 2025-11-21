from sanic import Blueprint
from sanic import response
from sanic.log import logger

health_router = Blueprint("health", url_prefix="/health")


@health_router.get("/")
async def health_check(request):
    """
    健康检查接口
    返回服务状态
    """
    logger.info("Health check requested")

    return response.json({
        "status": "ok"
    })
