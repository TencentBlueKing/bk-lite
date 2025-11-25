from celery import shared_task

from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants
from apps.node_mgmt.models import CloudRegionService
from apps.node_mgmt.utils.installer import exec_command_to_remote


def deploy_stargazer(ip, port, username, password):
    """部署 Stargazer 云服务器相关服务的任务"""
    install_command = ""
    exec_command_to_remote(CloudRegionConstants.DEFAULT_CLOUD_REGION_NAME, ip, username, password, install_command, port)


def deploy_nats_executor(ip, port, username, password):
    """部署 NATS Executor 云服务器相关服务的任务"""
    install_command = ""
    exec_command_to_remote(CloudRegionConstants.DEFAULT_CLOUD_REGION_NAME, ip, username, password, install_command, port)


DEPLOY_FUNC = {
    CloudRegionServiceConstants.STARGAZER_SERVICE_NAME: deploy_stargazer,
    CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME: deploy_nats_executor,
}


@shared_task
def deployed_cloud_server(data: dict):
    """
    云服务器部署任务
    开始部署时将部署状态改为“部署中”
    结束部署时将部署状态改为“已部署”或“部署失败”,并记录部署信息
    """
    ip = data["ip"]
    port = data["port"]
    username = data["username"]
    password = data["password"]
    service_name = data["service_name"]
    cloud_region_id = data["cloud_region_id"]

    deploy_func = DEPLOY_FUNC.get(service_name)

    if deploy_func:
        try:
            # 开始部署，更新状态为“部署中”
            CloudRegionService.objects.filter(cloud_region_id=cloud_region_id, name=service_name).update(
                deployed_status=CloudRegionServiceConstants.NOT_DEPLOYED_STATUS
            )

            # 执行部署任务
            deploy_func(ip, port, username, password)

            # 部署成功，更新状态为“已部署”
            # 具体实现省略
            CloudRegionService.objects.filter(cloud_region_id=cloud_region_id, name=service_name).update(
                deployed_status=CloudRegionServiceConstants.DEPLOYING
            )

        except Exception as e:
            CloudRegionService.objects.filter(cloud_region_id=cloud_region_id, name=service_name).update(
                deployed_status=CloudRegionServiceConstants.ERROR,
                deploy_message=str(e)
            )