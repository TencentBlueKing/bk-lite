import importlib
from unittest.mock import patch

import pytest
from django.apps import apps as django_apps

from apps.system_mgmt.models import LoginModule
from apps.system_mgmt.models.login_module import BK_LOGIN_APP_TOKEN_MASK
from apps.system_mgmt.nats.settings import verify_bk_token
from apps.system_mgmt.serializers.login_module_serializer import LoginModuleSerializer


pytestmark = pytest.mark.django_db


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
    assert login_module.decrypted_other_config["app_token"] == "blueking-secret"


def test_login_module_serializer_masks_app_token_and_preserves_it_on_update():
    login_module = LoginModule.objects.create(
        name="bk-login-serializer",
        source_type="bk_login",
        other_config=_bk_config(),
    )

    assert LoginModuleSerializer(login_module).data["other_config"]["app_token"] == BK_LOGIN_APP_TOKEN_MASK

    serializer = LoginModuleSerializer(
        login_module,
        data={"other_config": _bk_config(BK_LOGIN_APP_TOKEN_MASK)},
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    login_module.refresh_from_db()

    assert login_module.decrypted_other_config["app_token"] == "blueking-secret"


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


def test_data_migration_encrypts_existing_plaintext_app_token():
    login_module = LoginModule.objects.create(
        name="bk-login-migration",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config("legacy-plaintext"))

    migration = importlib.import_module("apps.system_mgmt.migrations.0040_encrypt_bk_login_app_token")
    migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] != "legacy-plaintext"
    assert login_module.decrypted_other_config["app_token"] == "legacy-plaintext"

    migration.decrypt_existing_bk_login_app_tokens(django_apps, None)
    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] == "legacy-plaintext"


def test_data_migration_stops_when_app_token_encryption_fails(monkeypatch):
    login_module = LoginModule.objects.create(
        name="bk-login-migration-failure",
        source_type="bk_login",
        other_config=_bk_config(),
    )
    LoginModule.objects.filter(pk=login_module.pk).update(other_config=_bk_config("legacy-plaintext"))
    migration = importlib.import_module("apps.system_mgmt.migrations.0040_encrypt_bk_login_app_token")
    monkeypatch.setattr(migration.EncryptMixin, "encrypt_field", lambda *args, **kwargs: None)

    with pytest.raises(RuntimeError, match="Failed to encrypt bk_login app_token"):
        migration.encrypt_existing_bk_login_app_tokens(django_apps, None)
