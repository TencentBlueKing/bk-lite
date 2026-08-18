import pytest

from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv
from apps.node_mgmt.serializers.sidecar_env import EnvVariableCreateSerializer, SidecarEnvSerializer


pytestmark = pytest.mark.django_db


@pytest.fixture
def cloud_region():
    return CloudRegion.objects.create(
        name="installer-credentials-mode-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )


def test_installer_credentials_mode_create_rejects_invalid_value(cloud_region):
    serializer = EnvVariableCreateSerializer(
        data={
            "key": NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY,
            "value": "typo",
            "type": EnvVariableConstants.TYPE_TEXT,
            "description": "installer credentials migration mode",
            "cloud_region_id": cloud_region.id,
        }
    )

    assert serializer.is_valid() is False
    assert serializer.errors["value"] == ["NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"]


def test_installer_credentials_mode_update_rejects_invalid_value(cloud_region):
    env = SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY,
        value=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=cloud_region,
    )
    serializer = SidecarEnvSerializer(instance=env, data={"value": "typo"}, partial=True)

    assert serializer.is_valid() is False
    assert serializer.errors["value"] == ["NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"]
