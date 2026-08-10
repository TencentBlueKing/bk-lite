import os
from apps.core.logger import node_logger as logger

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv, CloudRegionService


def cloud_init():
    """
    初始化云区域
    """
    try:
        CloudRegion.objects.update_or_create(
            id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
            defaults={
                "id": CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                "name": CloudRegionConstants.DEFAULT_CLOUD_REGION_NAME,
                "introduction": CloudRegionConstants.DEFAULT_CLOUD_REGION_INTRODUCTION,
            },
        )

        default_service_defaults = {
            CloudRegionServiceConstants.STARGAZER_SERVICE_NAME: {
                "status": CloudRegionServiceConstants.NORMAL,
                "deployed_status": CloudRegionServiceConstants.DEPLOYED,
            },
            CloudRegionServiceConstants.NATS_EXECUTOR_SERVICE_NAME: {
                "status": CloudRegionServiceConstants.NORMAL,
                "deployed_status": CloudRegionServiceConstants.DEPLOYED,
            },
        }

        # 初始化云区域下的服务
        for service_name in CloudRegionServiceConstants.SERVICES:
            CloudRegionService.objects.get_or_create(
                cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                name=service_name,
                defaults={
                    **default_service_defaults.get(
                        service_name,
                        {"status": CloudRegionServiceConstants.NOT_DEPLOYED},
                    ),
                    "description": f"Service {service_name} for default cloud region",
                },
            )

        aes_obj = AESCryptor()
        for key, value in dict(os.environ).items():
            if key.startswith(EnvVariableConstants.DEFAULT_ZONE_ENV_PREFIX):
                new_key = key.replace(EnvVariableConstants.DEFAULT_ZONE_ENV_PREFIX, "")
                stored_value, _type = value, EnvVariableConstants.TYPE_NORMAL
                if EnvVariableConstants.SENSITIVE_FIELD_KEYWORD in new_key.lower():
                    stored_value = aes_obj.encode(stored_value)
                    _type = EnvVariableConstants.TYPE_SECRET
                elif new_key in EnvVariableConstants.TEXT_KEYS:
                    _type = EnvVariableConstants.TYPE_TEXT
                env_var, created = SidecarEnv.objects.get_or_create(
                    key=new_key,
                    cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                    defaults={"value": stored_value, "cloud_region_id": CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, "is_pre": True, "type": _type},
                )
                if created or not env_var.is_pre:
                    continue

                value_changed = env_var.value != stored_value
                if _type == EnvVariableConstants.TYPE_SECRET:
                    try:
                        value_changed = aes_obj.decode(env_var.value) != value
                    except Exception:
                        value_changed = True
                update_fields = []
                if value_changed:
                    env_var.value = stored_value
                    update_fields.append("value")
                if env_var.type != _type:
                    env_var.type = _type
                    update_fields.append("type")
                if update_fields:
                    env_var.save(update_fields=update_fields)
                    logger.info("Synchronized preconfigured default-zone variable: %s", new_key)
    except Exception as e:
        logger.exception(e)
