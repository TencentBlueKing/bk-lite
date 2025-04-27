import os

from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv


def cloud_init():
    """
    初始化云区域
    """
    CloudRegion.objects.update_or_create(id=1, defaults={"id": 1, "name": "default", "introduction": "default cloud region!"})

    for key, value in os.environ.items():
        if key.startswith("DEFAULT_ZONE_VAR_"):
            new_key = key.replace("DEFAULT_ZONE_VAR_", "")
            SidecarEnv.objects.get_or_create(
                key=new_key,
                defaults={"value": value, "cloud_region_id": 1}
            )
