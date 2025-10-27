import os

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


def cloud_init():
    """
    初始化云区域
    """
    CloudRegion.objects.update_or_create(
        id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        defaults={
            "id": CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
            "name": CloudRegionConstants.DEFAULT_CLOUD_REGION_NAME,
            "introduction": CloudRegionConstants.DEFAULT_CLOUD_REGION_INTRODUCTION
        }
    )
    aes_obj = AESCryptor()
    for key, value in os.environ.items():
        if key.startswith(EnvVariableConstants.DEFAULT_ZONE_ENV_PREFIX):
            new_key = key.replace(EnvVariableConstants.DEFAULT_ZONE_ENV_PREFIX, "")
            stored_value, _type = value, EnvVariableConstants.TYPE_NORMAL
            if EnvVariableConstants.SENSITIVE_FIELD_KEYWORD in new_key.lower():
                stored_value = aes_obj.encode(stored_value)
                _type = EnvVariableConstants.TYPE_SECRET
            SidecarEnv.objects.get_or_create(
                key=new_key,
                cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                defaults={
                    "value": stored_value,
                    "cloud_region_id": CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
                    "is_pre": True,
                    "type": _type
                },
            )
