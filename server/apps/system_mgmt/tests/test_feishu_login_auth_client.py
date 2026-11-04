import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.core.logger import SafeLogException
from apps.core.utils.safe_requests import SafeRequestsError
from apps.core.utils.ssrf_validator import SSRFError
from apps.system_mgmt.providers.builtin.feishu.adapters.client import FEISHU_JSAPI_TOKEN_URL
from apps.system_mgmt.providers.builtin.feishu.adapters.login_auth import FeishuLoginAuthAdapter

CONFIG = {
    "app_id": "cli_public",
    "app_secret": "secret-sentinel",
}
JSAPI_REQUEST_FAILED = "Feishu JSAPI login request failed: endpoint=%s, error_type=%s"
DESCRIBE_FAILED = "event=login_auth_client_login_describe_failed provider_key=%s failed_stage=%s error_type=%s"
_LOG_FORMATTER = logging.Formatter("%(levelname)s %(name)s %(message)s")


def _rendered_logs(caplog):
    return "\n".join(_LOG_FORMATTER.format(record) for record in caplog.records)


def _assert_rendered_log(caplog, *, level, template, args, message, forbidden, expect_exc_info=False):
    matches = [record for record in caplog.records if record.msg == template]
    assert len(matches) == 1
    record = matches[0]
    assert record.levelno == level
    assert record.args == args
    assert record.getMessage() == message
    if expect_exc_info:
        assert record.exc_info is not None
        assert record.exc_info[0] is SafeLogException
        assert str(record.exc_info[1]) == args[-1]
        assert record.exc_info[2] is not None
    else:
        assert record.exc_info in (None, (None, None, None))
    formatted = _LOG_FORMATTER.format(record)
    blob = "\n".join([record.getMessage(), formatted, caplog.text, _rendered_logs(caplog)])
    for secret in forbidden:
        assert secret not in blob
    return record


def _json_response(payload, status_code=200):
    response = MagicMock(status_code=status_code)
    response.json.return_value = payload
    return response


def test_describe_client_login_exposes_app_id_and_both_evidence_modes():
    result = FeishuLoginAuthAdapter.describe_client_login(
        config=CONFIG,
        provider_key="feishu",
        capability_key="login_auth",
    )

    assert result.success is True
    assert result.payload == {
        "evidence_modes": ["oauth", "jsapi"],
        "jsapi": {"app_id": "cli_public"},
    }
    assert "secret-sentinel" not in str(result.payload)


def test_describe_client_login_is_empty_without_app_id():
    result = FeishuLoginAuthAdapter.describe_client_login(
        config={},
        provider_key="feishu",
        capability_key="login_auth",
    )

    assert result.payload == {"evidence_modes": []}


def test_oauth_code_still_uses_tenant_access_token_exchange():
    token_response = _json_response({"code": 0, "data": {"access_token": "user-token"}})
    user_response = _json_response({"code": 0, "data": {"user_id": "u1", "name": "Ada"}})

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        return_value=token_response,
    ) as post, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="oauth-code",
            binding=MagicMock(name="飞书登录"),
        )

    tenant.assert_called_once()
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tenant-token"
    assert post.call_args.kwargs["json"] == {"grant_type": "authorization_code", "code": "oauth-code"}
    assert result.success is True
    assert result.payload["external_user"]["user_id"] == "u1"


def test_request_access_code_uses_oauth_v3_without_tenant_token(caplog):
    token_response = _json_response({"code": 0, "access_token": "user-token"})
    user_response = _json_response({"code": 0, "data": {"user_id": "u2", "open_id": "o2"}})

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.safe_post",
        return_value=token_response,
    ) as post, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ) as get:
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
            jsapi_code_type="request_access",
        )

    tenant.assert_not_called()
    assert post.call_args.args[0] == FEISHU_JSAPI_TOKEN_URL
    assert post.call_args.kwargs["json"]["client_id"] == "cli_public"
    assert post.call_args.kwargs["json"]["client_secret"] == "secret-sentinel"
    assert post.call_args.kwargs["json"]["code"] == "jsapi-code"
    assert "redirect_uri" not in post.call_args.kwargs["json"]
    assert post.call_args.kwargs["timeout"] == 10
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer user-token"
    assert result.payload["external_user"]["open_id"] == "o2"
    rendered = _rendered_logs(caplog)
    assert rendered == ""
    assert "secret-sentinel" not in caplog.text
    assert "jsapi-code" not in caplog.text


def test_legacy_request_auth_code_keeps_tenant_exchange():
    token_response = _json_response({"code": 0, "data": {"access_token": "user-token"}})
    user_response = _json_response({"code": 0, "data": {"user_id": "u3"}})

    with patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ) as tenant, patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.post",
        return_value=token_response,
    ), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.requests.get",
        return_value=user_response,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="legacy-code",
            evidence_mode="jsapi",
            jsapi_code_type="request_auth_code",
        )

    tenant.assert_called_once()
    assert result.payload["external_user"]["user_id"] == "u3"


def test_request_access_failure_logs_endpoint_without_secret(caplog):
    err = SafeRequestsError("HTTP 请求失败")
    err.__cause__ = requests.ConnectionError("secret-sentinel")
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.safe_post",
        side_effect=err,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.request_failed"
    _assert_rendered_log(
        caplog,
        level=logging.DEBUG,
        template=JSAPI_REQUEST_FAILED,
        args=("https://accounts.feishu.cn", "ConnectionError"),
        message="Feishu JSAPI login request failed: endpoint=https://accounts.feishu.cn, error_type=ConnectionError",
        forbidden=("secret-sentinel", "jsapi-code"),
    )


@pytest.mark.parametrize(
    ("side_effect", "code", "field"),
    [
        (SSRFError("不允许访问环回地址"), "provider.invalid_config", "login_auth_jsapi_token_url"),
        (SSRFError("不允许访问元数据地址"), "provider.invalid_config", "login_auth_jsapi_token_url"),
        (SSRFError("不允许重定向"), "provider.invalid_config", "login_auth_jsapi_token_url"),
    ],
)
def test_request_access_rejects_ssrf_targets(side_effect, code, field, caplog):
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.safe_post",
        side_effect=side_effect,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config={
                **CONFIG,
                "login_auth_jsapi_token_url": "http://127.0.0.1/oauth/v3/token",
            },
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
        )

    assert result.success is False
    assert result.errors[0].code == code
    assert result.errors[0].field == field
    _assert_rendered_log(
        caplog,
        level=logging.DEBUG,
        template=JSAPI_REQUEST_FAILED,
        args=("http://127.0.0.1", "SSRFError"),
        message="Feishu JSAPI login request failed: endpoint=http://127.0.0.1, error_type=SSRFError",
        forbidden=("secret-sentinel", "jsapi-code"),
    )


def test_request_access_maps_timeout(caplog):
    timeout = requests.Timeout("timed out")
    err = SafeRequestsError("HTTP 请求失败: timed out")
    err.__cause__ = timeout
    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.providers.builtin.feishu.adapters.login_auth.safe_post",
        side_effect=err,
    ):
        result = FeishuLoginAuthAdapter.authenticate(
            config=CONFIG,
            provider_key="feishu",
            capability_key="login_auth",
            auth_code="jsapi-code",
            evidence_mode="jsapi",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.timeout"
    assert "secret-sentinel" not in caplog.text
    assert "jsapi-code" not in caplog.text


def test_describe_public_client_login_ignores_unregistered_provider_without_warning(caplog):
    from apps.system_mgmt.services.login_auth_binding_service import describe_public_client_login

    instance = MagicMock()
    instance.provider_key = "bk_lite_builtin"
    instance.get_runtime_config.return_value = {"secret-sentinel": "secret-sentinel"}

    with caplog.at_level(logging.DEBUG, logger="system-manager"), patch(
        "apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute",
        side_effect=ValueError("provider missing"),
    ):
        public = describe_public_client_login(instance)

    assert public == {"evidence_modes": []}
    rendered = _rendered_logs(caplog)
    assert DESCRIBE_FAILED not in rendered
    assert "secret-sentinel" not in rendered
    assert "secret-sentinel" not in caplog.text


def test_describe_public_client_login_logs_failure_without_secret(caplog):
    from apps.system_mgmt.services.login_auth_binding_service import describe_public_client_login

    instance = MagicMock()
    instance.provider_key = "feishu"
    instance.get_runtime_config.side_effect = RuntimeError("secret-sentinel")

    with caplog.at_level(logging.DEBUG, logger="system-manager"):
        public = describe_public_client_login(instance)

    assert public == {"evidence_modes": []}
    record = _assert_rendered_log(
        caplog,
        level=logging.WARNING,
        template=DESCRIBE_FAILED,
        args=("feishu", "describe_client_login", "RuntimeError"),
        message=("event=login_auth_client_login_describe_failed provider_key=feishu " "failed_stage=describe_client_login error_type=RuntimeError"),
        forbidden=("secret-sentinel",),
        expect_exc_info=True,
    )
    assert record.exc_info[2] is instance.get_runtime_config.side_effect.__traceback__


@pytest.mark.django_db
def test_public_binding_payload_includes_jsapi_app_id_only():
    from apps.system_mgmt.models import IntegrationInstance, IntegrationInstanceStatusChoices, LoginAuthBinding
    from apps.system_mgmt.services.login_auth_binding_service import serialize_public_login_auth_binding

    instance = IntegrationInstance.objects.create(
        name="Feishu",
        provider_key="feishu",
        config={"app_id": "cli_public", "app_secret": "secret-sentinel"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="飞书",
        integration_instance=instance,
        enabled=True,
        external_field="user_id",
        platform_field="username",
        unmatched_user_action="deny",
    )

    payload = serialize_public_login_auth_binding(binding)

    assert payload["client_login"] == {
        "evidence_modes": ["oauth", "jsapi"],
        "jsapi": {"app_id": "cli_public"},
    }
    assert "secret-sentinel" not in str(payload)
