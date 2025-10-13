import os

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


def cloud_init():
    """
    初始化云区域
    """
    CloudRegion.objects.update_or_create(id=1, defaults={"id": 1, "name": "default", "introduction": "default cloud region!"})
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
                cloud_region_id=1,
                defaults={"value": stored_value, "cloud_region_id": 1, "is_pre": True, "type": _type},
            )
