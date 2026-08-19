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


@pytest.mark.parametrize("value", ["", "   "])
def test_installer_credentials_reject_blank_values(cloud_region, value):
    for key in (
        NodeConstants.NATS_INSTALLER_USERNAME_KEY,
        NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
    ):
        serializer = EnvVariableCreateSerializer(
            data={
                "key": key,
                "value": value,
                "type": EnvVariableConstants.TYPE_TEXT,
                "description": "installer credential",
                "cloud_region_id": cloud_region.id,
            }
        )
        assert serializer.is_valid() is False
        assert serializer.errors["value"]


def test_renaming_plaintext_variable_to_installer_password_requires_new_value(cloud_region):
    env = SidecarEnv.objects.create(
        key="LEGACY_VARIABLE",
        value="legacy-plaintext",
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=cloud_region,
    )
    serializer = SidecarEnvSerializer(
        instance=env,
        data={"key": NodeConstants.NATS_INSTALLER_PASSWORD_KEY},
        partial=True,
    )

    assert serializer.is_valid() is False
    assert serializer.errors["value"] == ["A new NATS_INSTALLER_PASSWORD value is required"]


def test_installer_password_migration_resumes_across_failed_batches(cloud_region, monkeypatch):
    env = SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
        value="legacy-plaintext",
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=cloud_region,
    )
    assert InstallerSessionService._get_cloud_region_env(cloud_region.id)[env.key] == "legacy-plaintext"
    assert SidecarEnvSerializer(env).data["value"] == EnvVariableConstants.SECRET_MASK

    migration = import_module("apps.node_mgmt.migrations.0044_encrypt_installer_passwords")
    second_region = CloudRegion.objects.create(name="installer-credentials-mode-region-2")
    second_env = SidecarEnv.objects.create(
        key=NodeConstants.NATS_INSTALLER_PASSWORD_KEY,
        value="second-legacy-plaintext",
        type=EnvVariableConstants.TYPE_TEXT,
        cloud_region=second_region,
    )
    schema_editor = SimpleNamespace(connection=connection)
    real_cryptor = migration.AESCryptor

    class FailSecondBatchCryptor:
        def __init__(self):
            self.calls = 0

        def encode(self, value):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated second batch failure")
            return real_cryptor().encode(value)

    monkeypatch.setattr(migration, "BATCH_SIZE", 1)
    monkeypatch.setattr(migration, "AESCryptor", FailSecondBatchCryptor)
    with pytest.raises(RuntimeError, match="second batch failure"):
        migration.encrypt_installer_passwords(django_apps, schema_editor)
    env.refresh_from_db()
    first_ciphertext = env.value
    second_env.refresh_from_db()

    assert env.type == EnvVariableConstants.TYPE_SECRET
    assert AESCryptor().decode(env.value) == "legacy-plaintext"
    assert InstallerSessionService._get_cloud_region_env(cloud_region.id)[env.key] == "legacy-plaintext"
    assert second_env.type == EnvVariableConstants.TYPE_TEXT
    assert second_env.value == "second-legacy-plaintext"

    monkeypatch.setattr(migration, "AESCryptor", real_cryptor)
    migration.encrypt_installer_passwords(django_apps, schema_editor)
    env.refresh_from_db()
    second_env.refresh_from_db()
    assert env.value == first_ciphertext
    assert second_env.type == EnvVariableConstants.TYPE_SECRET
    assert AESCryptor().decode(second_env.value) == "second-legacy-plaintext"
