import requests
from apps.core.logger import celery_logger as logger

from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.rpc.executor import Executor

# 健康检查超时时间（秒）
HEALTH_CHECK_TIMEOUT = 10


def check_stargazer_health(cloud_region):
    """
    检查 Stargazer 服务健康状态（通过 HTTP）
    返回: (status, message) 元组
    """
    try:
        # 从预加载的环境变量中查找
        env_obj = None
        for env in cloud_region.sidecarenv_set.all():
            if env.key == "STARGAZER_URL":
                env_obj = env
                break

        if not env_obj:
            msg = f"云区域 {cloud_region.name} 未配置 STARGAZER_URL"
            logger.warning(msg)
            return CloudRegionServiceConstants.N_ERROR, msg

        url = f"{env_obj.value}/api/health"

        response = requests.get(url, timeout=HEALTH_CHECK_TIMEOUT)

        if response.status_code == 200:
            result = response.json()
            if result.get("status") == "ok":
                return CloudRegionServiceConstants.NORMAL, "服务正常"
            else:
                msg = f"健康检查返回异常状态: {result}"
                logger.warning(
                    f"Stargazer 健康检查失败，云区域: {cloud_region.name}, "
                    f"返回结果: {result}"
                )
                return CloudRegionServiceConstants.N_ERROR, msg
        else:
            msg = f"HTTP 请求失败，状态码: {response.status_code}"
            logger.warning(
                f"Stargazer 健康检查失败，云区域: {cloud_region.name}, "
                f"状态码: {response.status_code}"
            )
            return CloudRegionServiceConstants.N_ERROR, msg

    except requests.exceptions.Timeout:
        msg = "健康检查请求超时"
        logger.error(f"Stargazer 健康检查超时，云区域: {cloud_region.name}")
        return CloudRegionServiceConstants.N_ERROR, msg
    except Exception as e:
        msg = f"健康检查异常: {str(e)}"
        logger.error(
            f"Stargazer 健康检查异常，云区域: {cloud_region.name}, "
            f"错误: {str(e)}"
        )
        return CloudRegionServiceConstants.N_ERROR, msg


def check_nats_executor_health(cloud_region):
    """
    检查 NATS Executor 服务健康状态（通过 NATS 协议）
    返回: (status, message) 元组
    """
    try:
        # 使用云区域名称作为 executor 实例 ID
        instance_id = cloud_region.name

        # 使用 Executor 客户端进行健康检查
        executor = Executor(instance_id)
        result = executor.health_check(timeout=HEALTH_CHECK_TIMEOUT)

        # 根据返回结果判断健康状态
        if result and result.get("status") == "ok":
            return CloudRegionServiceConstants.NORMAL, "服务正常"
        else:
            msg = f"健康检查返回异常: {result}"
            logger.warning(
                f"NATS Executor 健康检查失败，云区域: {cloud_region.name}, "
                f"返回结果: {result}"
            )
            return CloudRegionServiceConstants.N_ERROR, msg

    except Exception as e:
        msg = f"健康检查异常: {str(e)}"
        logger.error(
            f"NATS Executor 健康检查异常，云区域: {cloud_region.name}, "
            f"错误: {str(e)}"
        )
        return CloudRegionServiceConstants.N_ERROR, msg


SERVICES_FUNC = {
    CloudRegionServiceConstants.STARGAZER_SERVICE_NAME: check_stargazer_health,
    CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME: check_nats_executor_health,
}
