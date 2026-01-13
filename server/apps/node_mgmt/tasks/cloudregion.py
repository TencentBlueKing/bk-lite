from celery import shared_task
from apps.core.logger import celery_logger as logger
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.models import CloudRegion, CloudRegionService
from apps.node_mgmt.tasks.services.cloud_service_check_health import SERVICES_FUNC


@shared_task
def check_all_region_services():
    """
    遍历所有云区域服务记录 -> 执行对应的健康检查 -> 批量更新状态
    """
    regions = CloudRegion.objects.prefetch_related('cloudregionservice_set', 'sidecarenv_set').all()
    services_to_update = []

    for region in regions:
        for service in region.cloudregionservice_set.all():

            # 根据服务名称查找对应的健康检查函数
            health_check_func = SERVICES_FUNC.get(service.name)
            if health_check_func:
                status, message = health_check_func(region)
                if status == CloudRegionServiceConstants.NORMAL:
                    service.deployed_status = CloudRegionServiceConstants.DEPLOYED
                service.status = status
                service.message = message
                services_to_update.append(service)

    # 批量更新所有服务状态
    if services_to_update:
        CloudRegionService.objects.bulk_update(services_to_update, ['status', 'deployed_status', 'message'])
        logger.info(f"批量更新了 {len(services_to_update)} 个云区域服务的健康状态")
