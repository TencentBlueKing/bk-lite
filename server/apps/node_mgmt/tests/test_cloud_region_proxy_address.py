import pytest

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import CloudRegionConstants, EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models import CloudRegion, SidecarEnv
from apps.node_mgmt.nats.node import get_cloud_region_proxy_address
from apps.node_mgmt.services.cloudregion import RegionService


def _create_cloud_region(region_id: int, name: str, proxy_address: str = ""):
    return CloudRegion.objects.create(
        id=region_id,
        name=name,
        introduction=f"{name} intro",
        proxy_address=proxy_address,
        created_by="tester",
        updated_by="tester",
    )


@pytest.mark.django_db
def test_get_cloud_region_proxy_address_prefers_cloud_region_field():
    cloud_region = _create_cloud_region(101, "region-101", proxy_address="proxy.example.com")
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
        value="env.example.com",
        type=EnvVariableConstants.TYPE_NORMAL,
    )

    assert get_cloud_region_proxy_address(str(cloud_region.id)) == "proxy.example.com"


@pytest.mark.django_db
def test_get_cloud_region_proxy_address_falls_back_to_env_var():
    cloud_region = _create_cloud_region(102, "region-102")
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
        value="env.example.com",
        type=EnvVariableConstants.TYPE_NORMAL,
    )

    assert get_cloud_region_proxy_address(str(cloud_region.id)) == "env.example.com"


@pytest.mark.django_db
def test_get_cloud_region_proxy_address_decrypts_secret_env_var():
    cloud_region = _create_cloud_region(103, "region-103")
    aes = AESCryptor()
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key=EnvVariableConstants.PROXY_ADDRESS_KEY,
        value=aes.encode("secret.example.com"),
        type=EnvVariableConstants.TYPE_SECRET,
    )

    assert get_cloud_region_proxy_address(str(cloud_region.id)) == "secret.example.com"


@pytest.mark.django_db
def test_get_cloud_region_proxy_address_returns_empty_when_missing():
    cloud_region = _create_cloud_region(104, "region-104")

    assert get_cloud_region_proxy_address(str(cloud_region.id)) == ""


@pytest.mark.django_db
def test_init_env_vars_creates_proxy_address_env_var():
    _create_cloud_region(CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, "default")
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://default.example.com:443",
        type=EnvVariableConstants.TYPE_NORMAL,
        is_pre=True,
    )
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://default.example.com:4222",
        type=EnvVariableConstants.TYPE_NORMAL,
        is_pre=True,
    )

    cloud_region = _create_cloud_region(105, "region-105", proxy_address="proxy.example.com")

    RegionService.init_env_vars(cloud_region.id)

    proxy_env = SidecarEnv.objects.get(cloud_region=cloud_region, key=EnvVariableConstants.PROXY_ADDRESS_KEY)
    assert proxy_env.value == "proxy.example.com"
    assert proxy_env.type == EnvVariableConstants.TYPE_NORMAL
    assert proxy_env.is_pre is False


@pytest.mark.django_db
def test_update_env_vars_on_proxy_change_updates_proxy_related_env_vars():
    _create_cloud_region(CloudRegionConstants.DEFAULT_CLOUD_REGION_ID, "default")
    SidecarEnv.objects.create(
        cloud_region_id=CloudRegionConstants.DEFAULT_CLOUD_REGION_ID,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://default.example.com:443",
        type=EnvVariableConstants.TYPE_NORMAL,
        is_pre=True,
    )

    cloud_region = _create_cloud_region(106, "region-106")
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key=NodeConstants.SERVER_URL_KEY,
        value="https://default.example.com:443",
        type=EnvVariableConstants.TYPE_NORMAL,
    )
    SidecarEnv.objects.create(
        cloud_region=cloud_region,
        key=NodeConstants.NATS_SERVERS_KEY,
        value="nats://default.example.com:4222",
        type=EnvVariableConstants.TYPE_NORMAL,
    )

    updated_count = RegionService.update_env_vars_on_proxy_change(
        cloud_region_id=cloud_region.id,
        old_proxy_address="",
        new_proxy_address="proxy.example.com",
    )

    assert updated_count == 3
    assert SidecarEnv.objects.get(cloud_region=cloud_region, key=EnvVariableConstants.PROXY_ADDRESS_KEY).value == "proxy.example.com"
    assert SidecarEnv.objects.get(cloud_region=cloud_region, key=NodeConstants.SERVER_URL_KEY).value == "https://proxy.example.com:443"
    assert SidecarEnv.objects.get(cloud_region=cloud_region, key=NodeConstants.NATS_SERVERS_KEY).value == "nats://proxy.example.com:4222"
