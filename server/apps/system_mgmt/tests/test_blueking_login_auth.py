import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.system_mgmt.providers.builtin.blueking.adapters.login_auth import BlueKingLoginAuthAdapter

CONFIG = {
    "bk_url": "https://bk.example.com",
    "app_id": "bk-app",
    "app_token": "app-token-sentinel-SECRET",
    "bk_username": "bk-sync-user",
}
BK_TOKEN = "bk-token-sentinel-SECRET"
RESPONSE_BODY_SENTINEL = "must-not-log-blueking-login-body"
BINDING_NAME_SENTINEL = "must-not-log-binding-name"
_FAILED_TEMPLATE = "event=blueking_login_auth_failed binding_id=%s failed_stage=%s error_type=%s"


def response(payload, status_code=200):
    item = MagicMock()
    item.status_code = status_code
    item.json.return_value = payload
    return item


def test_authenticate_returns_username_for_valid_bk_token():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response({"result": True, "data": {"bk_username": "alice"}}),
    ) as get:
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            bk_token=BK_TOKEN,
        )

    assert result.success is True
    assert result.payload == {"external_user": {"username": "alice"}}
    assert get.call_args.args[0] == "https://bk.example.com/api/c/compapi/v2/bk_login/get_user/"
    assert get.call_args.kwargs["params"]["bk_app_code"] == "bk-app"
    assert get.call_args.kwargs["params"]["bk_app_secret"] == CONFIG["app_token"]
    assert get.call_args.kwargs["params"]["bk_token"] == BK_TOKEN
    assert "bk_username" not in get.call_args.kwargs["params"]


def test_authenticate_accepts_username_field_from_get_user():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response({"result": True, "data": {"username": "bob"}}),
    ):
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            bk_token=BK_TOKEN,
        )

    assert result.success is True
    assert result.payload["external_user"] == {"username": "bob"}


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        ({}, "provider.invalid_config"),
        ({"bk_token": ""}, "provider.invalid_config"),
        ({"bk_token": BK_TOKEN}, "provider.auth_failed"),
    ],
)
def test_authenticate_returns_stable_error_codes(kwargs, expected_code):
    payload = {"result": False, "message": RESPONSE_BODY_SENTINEL, "data": {}}
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response(payload),
    ) as get:
        result = BlueKingLoginAuthAdapter.authenticate(CONFIG, "blueking", "login_auth", **kwargs)

    assert result.success is False
    assert result.errors[0].code == expected_code
    if expected_code == "provider.invalid_config":
        get.assert_not_called()
        assert result.errors[0].field == "bk_token"


_TRANSPORT_TEMPLATE = "event=blueking_request_failed failed_stage=%s error_type=%s"


def _transport_records(caplog):
    return [record for record in caplog.records if record.name == "system-manager" and record.msg == _TRANSPORT_TEMPLATE]


def _raise_with_secret(exception_type, secret_url, caught):
    try:
        raise exception_type(secret_url)
    except exception_type as error:
        caught["error"] = error
        raise


def test_authenticate_timeout_logs_one_sanitized_traceback(caplog):
    secret_url = f"https://bk.example.com/?bk_app_secret={CONFIG['app_token']}&bk_token={BK_TOKEN}"
    caught = {}
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=lambda *args, **kwargs: _raise_with_secret(requests.Timeout, secret_url, caught),
    ):
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            bk_token=BK_TOKEN,
            binding=SimpleNamespace(id=19, name=BINDING_NAME_SENTINEL),
        )

    assert result.success is False
    assert result.errors[0].code == "provider.timeout"
    assert result.retryable is True
    assert _failure_records(caplog) == []
    records = _transport_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.args == ("esb_get", "Timeout")
    assert record.getMessage() == "event=blueking_request_failed failed_stage=esb_get error_type=Timeout"
    assert record.exc_info[0].__name__ == "SafeLogException"
    assert record.exc_info[2] is caught["error"].__traceback__
    assert record.exc_info[1] is not caught["error"]
    assert str(caught["error"]) == secret_url
    assert str(record.exc_info[1]) == "Timeout"
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    assert "Traceback" in formatted
    assert BK_TOKEN not in formatted
    assert CONFIG["app_token"] not in formatted
    assert secret_url not in formatted
    assert BINDING_NAME_SENTINEL not in formatted


def test_authenticate_request_failure_logs_one_sanitized_traceback(caplog):
    secret_url = f"https://bk.example.com/?bk_app_secret={CONFIG['app_token']}&bk_token={BK_TOKEN}"
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=lambda *args, **kwargs: _raise_with_secret(requests.ConnectionError, secret_url, {}),
    ):
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            bk_token=BK_TOKEN,
        )

    assert result.success is False
    assert result.errors[0].code == "provider.request_failed"
    assert result.retryable is True
    assert _failure_records(caplog) == []
    records = _transport_records(caplog)
    assert len(records) == 1
    assert records[0].args == ("esb_get", "request_failed")
    formatted = logging.Formatter("%(levelname)s %(message)s").format(records[0])
    assert secret_url not in formatted
    assert BK_TOKEN not in formatted
    assert CONFIG["app_token"] not in formatted


def _failure_records(caplog):
    return [record for record in caplog.records if record.name == "system-manager" and record.msg == _FAILED_TEMPLATE]


def test_authenticate_logs_binding_id_and_omits_tokens(caplog):
    payload = {
        "result": False,
        "message": RESPONSE_BODY_SENTINEL,
        "data": {"detail": RESPONSE_BODY_SENTINEL},
    }
    binding = SimpleNamespace(id=19, name=BINDING_NAME_SENTINEL)
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response(payload),
    ):
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            bk_token=BK_TOKEN,
            binding=binding,
        )

    assert result.success is False
    assert result.errors[0].code == "provider.auth_failed"
    records = _failure_records(caplog)
    assert len(records) == 1
    record = records[0]
    assert record.args == ("19", "authenticate", "auth_rejected")
    rendered = record.getMessage()
    assert rendered == "event=blueking_login_auth_failed binding_id=19 failed_stage=authenticate error_type=auth_rejected"
    assert record.exc_info in (None, (None, None, None))
    for text in (rendered, str(record.args)):
        assert BK_TOKEN not in text
        assert CONFIG["app_token"] not in text
        assert RESPONSE_BODY_SENTINEL not in text
        assert BINDING_NAME_SENTINEL not in text
    formatted = logging.Formatter("%(levelname)s %(message)s").format(record)
    assert BK_TOKEN not in formatted
    assert CONFIG["app_token"] not in formatted
    assert RESPONSE_BODY_SENTINEL not in formatted
    assert BINDING_NAME_SENTINEL not in formatted
    assert "bk_app_secret" not in formatted


def test_authenticate_missing_token_logs_binding_id(caplog):
    binding = SimpleNamespace(id=7, name=BINDING_NAME_SENTINEL)
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
    ) as get:
        result = BlueKingLoginAuthAdapter.authenticate(
            CONFIG,
            "blueking",
            "login_auth",
            binding=binding,
        )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "bk_token"
    get.assert_not_called()
    records = _failure_records(caplog)
    assert len(records) == 1
    assert records[0].args == ("7", "authenticate", "missing_token")
    rendered = records[0].getMessage()
    assert rendered == "event=blueking_login_auth_failed binding_id=7 failed_stage=authenticate error_type=missing_token"
    assert BINDING_NAME_SENTINEL not in rendered
    assert BK_TOKEN not in rendered


def test_connection_test_sends_configured_username_without_bk_token():
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response({"result": True, "data": {"count": 1, "results": []}}),
    ) as get:
        result = BlueKingLoginAuthAdapter.test_connection(CONFIG, "blueking", "login_auth")

    assert result.success is True
    params = get.call_args.kwargs["params"]
    assert get.call_args.args[0] == "https://bk.example.com/api/c/compapi/v2/usermanage/list_departments/"
    assert params["bk_username"] == "admin"
    assert params["page"] == 1
    assert params["page_size"] == 1
    assert "bk_token" not in params


def test_connection_test_uses_admin_even_when_config_has_another_username():
    config = {**CONFIG, "bk_username": "bk-sync-user"}
    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=response({"result": True, "data": {"count": 1, "results": []}}),
    ) as get:
        result = BlueKingLoginAuthAdapter.test_connection(config, "blueking", "login_auth")

    assert result.success is True
    assert get.call_args.kwargs["params"]["bk_username"] == "admin"


def test_build_login_url_stays_unimplemented():
    result = BlueKingLoginAuthAdapter.build_login_url(CONFIG, "blueking", "login_auth")

    assert result.success is False
    assert result.errors[0].code == "provider.operation_not_implemented"
