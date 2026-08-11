import importlib
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps

from apps.system_mgmt.models import LoginModule
from apps.system_mgmt.models.login_module import BK_LOGIN_APP_TOKEN_ENVELOPE_KEY
from apps.system_mgmt.nats.settings import verify_bk_token


pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _bk_config(app_token="blueking-secret"):
    return {
        "app_id": "bk-lite",
        "app_token": app_token,
        "bk_url": "https://bk.example.com",
        "root_group": "蓝鲸",
        "default_roles": [],
    }


def test_bk_login_app_token_is_encrypted_at_rest_and_decrypted_for_runtime():
    login_module = LoginModule.objects.create(
        name="bk-login-security",
        source_type="bk_login",
        other_config=_bk_config(),
    )

    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] != "blueking-secret"
    assert BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in login_module.other_config["app_token"]
    assert login_module.decrypted_other_config["app_token"] == "blueking-secret"


def test_bk_login_rejects_non_string_app_token_before_saving():
    with pytest.raises(ValueError, match="bk_login app_token must be a string"):
        LoginModule.objects.create(
            name="bk-login-invalid-token",
            source_type="bk_login",
            other_config=_bk_config(123),
        )

    assert LoginModule.objects.filter(name="bk-login-invalid-token").exists() is False


def test_verify_bk_token_uses_decrypted_app_token():
    LoginModule.objects.create(
        name="bk-login-runtime",
        source_type="bk_login",
        other_config=_bk_config(),
        enabled=True,
    )

    with patch(
        "apps.system_mgmt.nats.settings.get_bk_user_info",
        return_value=(False, None),
    ) as get_bk_user_info:
        result = verify_bk_token("bk-user-token")

    assert result["result"] is True
    get_bk_user_info.assert_called_once_with(
        "bk-user-token",
        "bk-lite",
        "blueking-secret",
        "https://bk.example.com",
    )


def test_verify_bk_token_keeps_plaintext_records_compatible_before_migration():
    login_module = LoginModule.objects.create(
        name="bk-login-legacy-runtime",
        source_type="bk_login",
        other_config=_bk_config(),
        enabled=True,
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config("legacy-plaintext"))

    with patch(
        "apps.system_mgmt.nats.settings.get_bk_user_info",
        return_value=(False, None),
    ) as get_bk_user_info:
        result = verify_bk_token("bk-user-token")

    assert result["result"] is True
    get_bk_user_info.assert_called_once_with(
        "bk-user-token",
        "bk-lite",
        "legacy-plaintext",
        "https://bk.example.com",
    )


def test_verify_bk_token_keeps_unversioned_encrypted_records_compatible():
    login_module = LoginModule.objects.create(
        name="bk-login-unversioned-runtime",
        source_type="bk_login",
        other_config=_bk_config(),
        enabled=True,
    )
    old_config = _bk_config("old-encrypted-secret")
    LoginModule.encrypt_field("app_token", old_config)
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=old_config)

    with patch(
        "apps.system_mgmt.nats.settings.get_bk_user_info",
        return_value=(False, None),
    ) as get_bk_user_info:
        result = verify_bk_token("bk-user-token")

    assert result["result"] is True
    get_bk_user_info.assert_called_once_with(
        "bk-user-token",
        "bk-lite",
        "old-encrypted-secret",
        "https://bk.example.com",
    )


def test_verify_bk_token_fails_closed_for_corrupted_app_token_envelope():
    login_module = LoginModule.objects.create(
        name="bk-login-corrupted-runtime",
        source_type="bk_login",
        other_config=_bk_config(),
        enabled=True,
    )
    corrupted_config = _bk_config({BK_LOGIN_APP_TOKEN_ENVELOPE_KEY: {"version": 1, "ciphertext": "invalid"}})
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=corrupted_config)

    with patch("apps.system_mgmt.nats.settings.get_bk_user_info") as get_bk_user_info, pytest.raises(
        ValueError, match="Failed to decrypt bk_login app_token"
    ):
        verify_bk_token("bk-user-token")

    get_bk_user_info.assert_not_called()


def test_data_migration_encrypts_existing_plaintext_app_token():
    login_module = LoginModule.objects.create(
        name="bk-login-migration",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config("legacy-plaintext"))

    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")
    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
    first_encrypted_value = LoginModule.objects.get(pk=login_module.pk).other_config["app_token"]
    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] != "legacy-plaintext"
    assert login_module.other_config["app_token"] == first_encrypted_value
    assert BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in login_module.other_config["app_token"]
    assert login_module.decrypted_other_config["app_token"] == "legacy-plaintext"

    migration.decrypt_existing_bk_login_app_tokens(django_apps, None)
    migration.decrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] == "legacy-plaintext"


def test_data_migration_preserves_plaintext_that_looks_like_a_legacy_prefix():
    plaintext = "bklite:v1:not-a-fernet-token"
    login_module = LoginModule.objects.create(
        name="bk-login-prefix-collision",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config(plaintext))
    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")

    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.decrypted_other_config["app_token"] == plaintext


def test_data_migration_uses_a_stable_cursor_across_batches(monkeypatch):
    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")
    monkeypatch.setattr(migration, "BATCH_SIZE", 2)
    LoginModule.objects.bulk_create(
        [
            LoginModule(name=f"bk-login-batch-{index}", source_type="bk_login", other_config=_bk_config())
            for index in range(migration.BATCH_SIZE + 1)
        ]
    )

    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)

    app_tokens = LoginModule.objects.filter(name__startswith="bk-login-batch-").values_list(
        "other_config__app_token", flat=True
    )
    assert len(app_tokens) == migration.BATCH_SIZE + 1
    assert all(BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in value for value in app_tokens)


def test_data_migration_upgrades_unversioned_encrypted_app_token_and_rolls_back():
    login_module = LoginModule.objects.create(
        name="bk-login-unversioned-migration",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    old_config = _bk_config("old-encrypted-secret")
    LoginModule.encrypt_field("app_token", old_config)
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=old_config)
    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")

    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in login_module.other_config["app_token"]
    assert login_module.decrypted_other_config["app_token"] == "old-encrypted-secret"

    migration.decrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] == "old-encrypted-secret"


def test_data_migration_stops_when_app_token_encryption_fails(monkeypatch):
    login_module = LoginModule.objects.create(
        name="bk-login-migration-failure",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config("legacy-plaintext"))
    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")
    monkeypatch.setattr(migration.EncryptMixin, "encrypt_field", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="Failed to encrypt bk_login app_token during migration"):
        migration.encrypt_existing_bk_login_app_tokens(django_apps, None)


def test_data_migration_fails_closed_for_corrupted_app_token_envelope():
    login_module = LoginModule.objects.create(
        name="bk-login-migration-corrupted",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    corrupted_config = _bk_config({BK_LOGIN_APP_TOKEN_ENVELOPE_KEY: {"version": 1, "ciphertext": "invalid"}})
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=corrupted_config)
    migration = importlib.import_module("apps.system_mgmt.migrations.0046_encrypt_bk_login_app_token")

    with pytest.raises(RuntimeError, match="Failed to decrypt bk_login app_token during migration"):
        migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
