import os

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import CloudRegionConstants
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
        if key.startswith("DEFAULT_ZONE_VAR_"):
            new_key = key.replace("DEFAULT_ZONE_VAR_", "")
            stored_value, _type = value, ""
            if "password" in new_key.lower():
                stored_value = aes_obj.encode(stored_value)
                _type = 'secret'
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
