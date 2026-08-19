from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps as django_apps
from django.db import connection

from apps.core.utils.crypto.aes_crypto import AESCryptor
from apps.node_mgmt.constants.database import EnvVariableConstants
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.cloud_region import CloudRegion, SidecarEnv
from apps.node_mgmt.serializers.sidecar_env import EnvVariableCreateSerializer, SidecarEnvSerializer
from apps.node_mgmt.services.installer_session import InstallerSessionService


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def cloud_region():
    return CloudRegion.objects.create(
        name="installer-credentials-mode-region",
        introduction="test",
        created_by="tester",
        updated_by="tester",
    )


@pytest.mark.parametrize("invalid_value", ["", "   ", "typo"])
def test_installer_credentials_mode_create_rejects_invalid_value(cloud_region, invalid_value):
    serializer = EnvVariableCreateSerializer(
        data={
            "key": NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY,
            "value": invalid_value,
            "type": EnvVariableConstants.TYPE_TEXT,
            "description": "installer credentials migration mode",
            "cloud_region_id": cloud_region.id,
        }
    )

    assert serializer.is_valid() is False
    assert serializer.errors["value"]
    if invalid_value == "typo":
        assert serializer.errors["value"] == ["NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"]


@pytest.mark.parametrize("invalid_value", ["", "   ", "typo"])
def test_installer_credentials_mode_update_rejects_invalid_value(cloud_region, invalid_value):
    env = SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_KEY,
        value=NodeConstants.NATS_INSTALLER_CREDENTIALS_MODE_STRICT,
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=cloud_region,
    )
    serializer = SidecarEnvSerializer(instance=env, data={"value": invalid_value}, partial=True)

    assert serializer.is_valid() is False
    assert serializer.errors["value"]
    if invalid_value == "typo":
        assert serializer.errors["value"] == ["NATS_INSTALLER_CREDENTIALS_MODE must be legacy or strict"]


def test_installer_password_create_forces_encrypted_secret(cloud_region):
    serializer = EnvVariableCreateSerializer(
        data={
            "key": NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
            "value": "installer-password",
            "type": EnvVariableConstants.TYPE_TEXT,
            "description": "installer credential",
            "cloud_region_id": cloud_region.id,
        }
    )

    assert serializer.is_valid(), serializer.errors
    env = serializer.save()
    assert env.type == EnvVariableConstants.TYPE_SECRET
    assert env.value != "installer-password"
    assert AESCryptor().decode(env.value) == "installer-password"
    assert SidecarEnvSerializer(env).data["value"] == EnvVariableConstants.SECRET_MASK


def test_installer_password_migration_is_idempotent_and_rollback_compatible(cloud_region):
    env = SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
        value="legacy-plaintext",
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=cloud_region,
    )
    assert InstallerSessionService._get_cloud_region_env(cloud_region.id)[env.key] == "legacy-plaintext"
    assert SidecarEnvSerializer(env).data["value"] == EnvVariableConstants.SECRET_MASK

    migration = import_module("apps.node_mgmt.migrations.0044_encrypt_installer_passwords")
    schema_editor = SimpleNamespace(connection=connection)
    migration.encrypt_installer_passwords(django_apps, schema_editor)
    env.refresh_from_db()
    first_ciphertext = env.value

    assert env.type == EnvVariableConstants.TYPE_SECRET
    assert AESCryptor().decode(env.value) == "legacy-plaintext"
    assert InstallerSessionService._get_cloud_region_env(cloud_region.id)[env.key] == "legacy-plaintext"

    migration.encrypt_installer_passwords(django_apps, schema_editor)
    env.refresh_from_db()
    assert env.value == first_ciphertext
