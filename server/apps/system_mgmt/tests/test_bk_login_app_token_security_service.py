from unittest.mock import patch

import pytest
from django.test import override_settings

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


def test_default_rollout_keeps_plaintext_writes_compatible():
    login_module = LoginModule.objects.create(
        name="bk-login-default-compatible",
        source_type="bk_login",
        other_config=_bk_config(),
    )

    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] == "blueking-secret"


@override_settings(BK_LOGIN_APP_TOKEN_ENCRYPTION_ENABLED=True)
def test_enabled_rollout_encrypts_at_rest_and_decrypts_for_runtime():
    login_module = LoginModule.objects.create(
        name="bk-login-security",
        source_type="bk_login",
        other_config=_bk_config(),
    )

    login_module.refresh_from_db()

    assert login_module.other_config["app_token"] != "blueking-secret"
    assert BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in login_module.other_config["app_token"]
    assert login_module.decrypted_other_config["app_token"] == "blueking-secret"


@override_settings(BK_LOGIN_APP_TOKEN_ENCRYPTION_ENABLED=True)
@pytest.mark.parametrize("invalid_token", [0, False, [], {}])
def test_enabled_rollout_rejects_non_string_app_token(invalid_token):
    with pytest.raises(ValueError, match="app_token"):
        LoginModule.objects.create(
            name=f"bk-login-invalid-{type(invalid_token).__name__}",
            source_type="bk_login",
            other_config=_bk_config(invalid_token),
        )


@override_settings(BK_LOGIN_APP_TOKEN_ENCRYPTION_ENABLED=True)
def test_enabled_rollout_stops_when_encryption_fails(monkeypatch):
    monkeypatch.setattr(LoginModule, "encrypt_field", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="Failed to encrypt bk_login app_token"):
        LoginModule.objects.create(
            name="bk-login-encryption-failure",
            source_type="bk_login",
            other_config=_bk_config(),
        )


def test_verify_bk_token_keeps_plaintext_records_compatible():
    LoginModule.objects.create(
        name="bk-login-legacy-runtime",
        source_type="bk_login",
        other_config=_bk_config("legacy-plaintext"),
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
        "legacy-plaintext",
        "https://bk.example.com",
    )


def test_verify_bk_token_keeps_unversioned_encrypted_records_compatible():
    old_config = _bk_config("old-encrypted-secret")
    LoginModule.encrypt_field("app_token", old_config)
    LoginModule.objects.create(
        name="bk-login-unversioned-runtime",
        source_type="bk_login",
        other_config=old_config,
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
        "old-encrypted-secret",
        "https://bk.example.com",
    )


def test_verify_bk_token_uses_envelope_after_flag_is_rolled_back():
    with override_settings(BK_LOGIN_APP_TOKEN_ENCRYPTION_ENABLED=True):
        login_module = LoginModule.objects.create(
            name="bk-login-envelope-runtime",
            source_type="bk_login",
            other_config=_bk_config(),
            enabled=True,
        )

    login_module.name = "bk-login-envelope-after-rollback"
    login_module.save()
    login_module.refresh_from_db()

    with patch(
        "apps.system_mgmt.nats.settings.get_bk_user_info",
        return_value=(False, None),
    ) as get_bk_user_info:
        result = verify_bk_token("bk-user-token")

    assert result["result"] is True
    assert BK_LOGIN_APP_TOKEN_ENVELOPE_KEY in login_module.other_config["app_token"]
    get_bk_user_info.assert_called_once_with(
        "bk-user-token",
        "bk-lite",
        "blueking-secret",
        "https://bk.example.com",
    )


def test_verify_bk_token_fails_closed_for_corrupted_app_token_envelope():
    LoginModule.objects.create(
        name="bk-login-corrupted-runtime",
        source_type="bk_login",
        other_config=_bk_config({BK_LOGIN_APP_TOKEN_ENVELOPE_KEY: {"version": 1, "ciphertext": "invalid"}}),
        enabled=True,
    )

    with patch("apps.system_mgmt.nats.settings.get_bk_user_info") as get_bk_user_info, pytest.raises(
        ValueError, match="Failed to decrypt bk_login app_token"
    ):
        verify_bk_token("bk-user-token")

    get_bk_user_info.assert_not_called()
