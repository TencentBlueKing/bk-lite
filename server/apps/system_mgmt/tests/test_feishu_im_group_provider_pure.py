import logging
from unittest import mock

import pytest
import requests

from apps.system_mgmt.providers.adapters.feishu import FeishuIMGroupAdapter
from apps.system_mgmt.providers.manifests.feishu import PROVIDER_MANIFEST

pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, payload, status_code=200, request_id="req-1"):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"X-Tt-Logid": request_id}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_feishu_manifest_declares_im_group_capability():
    capability = PROVIDER_MANIFEST.get_capability("im_group")

    assert capability.adapter_key == "feishu.im_group"
    assert capability.adapter_path.endswith("FeishuIMGroupAdapter")
    assert capability.connection_template == []


def test_connection_rejects_token_only_when_application_lacks_group_scopes():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse(
            {
                "code": 0,
                "data": {
                    "app": {
                        "scopes": ["application:application:self_manage"],
                        "bot": {"enabled": True},
                    }
                },
            }
        ),
    ) as get:
        result = FeishuIMGroupAdapter.test_connection(
            config={
                "im_group_application_info_url": "https://attacker.example/application/me",
                "im_group_bot_info_url": "https://attacker.example/bot/info",
            },
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.errors[0].code == "provider.permission_unverified"
    assert result.payload["missing_requirements"] == [
        "chat_create",
        "chat_read",
        "member_write",
        "message_send",
        "operate_as_owner",
    ]
    assert result.payload["external_request_id"] == "req-1"
    assert get.call_args.args == (
        "https://open.feishu.cn/open-apis/application/v6/applications/me",
    )
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tenant-token"


def test_connection_keeps_existing_invalid_config_contract():
    result = FeishuIMGroupAdapter.test_connection(
        config={},
        provider_key="feishu",
        capability_key="im_group",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "app_id"


def test_connection_rejects_disabled_bot_after_accepting_object_scopes():
    granted_scopes = [
        {"scope_name": scope}
        for scope in (
            "application:application:self_manage",
            "im:chat:create",
            "im:chat:read",
            "im:chat.members:write_only",
            "im:message:send_as_bot",
            "im:chat:operate_as_owner",
        )
    ]
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=[
            FakeResponse({"code": 0, "data": {"app": {"scopes": granted_scopes}}}, request_id="req-app"),
            FakeResponse(
                {"code": 0, "bot": {"activate_status": 1, "open_id": "ou_bot"}},
                request_id="req-bot",
            ),
        ],
    ) as get:
        result = FeishuIMGroupAdapter.test_connection(
            config={
                "im_group_application_info_url": "https://provider.example/application/me",
                "im_group_bot_info_url": "https://provider.example/bot/info",
            },
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.errors[0].code == "provider.bot_not_enabled"
    assert result.payload == {
        "missing_requirements": ["bot_enabled"],
        "external_request_id": "req-bot",
    }
    assert get.call_count == 2
    assert get.call_args.args == (
        "https://open.feishu.cn/open-apis/bot/v3/info",
    )


def test_connection_does_not_accept_explicitly_ungranted_scope_objects():
    scopes = [
        {"scope_name": "application:application:self_manage", "grant_status": 1},
        {"scope_name": "im:chat:create", "grant_status": 0},
        {"scope_name": "im:chat:read", "grant_status": 1},
        {"scope_name": "im:chat.members:write_only", "grant_status": 1},
        {"scope_name": "im:message:send_as_bot", "grant_status": 1},
        {"scope_name": "im:chat:operate_as_owner", "grant_status": 1},
    ]
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse({"code": 0, "data": {"app": {"scopes": scopes}}}),
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.permission_unverified"
    assert result.payload["missing_requirements"] == ["chat_create"]


def test_connection_is_ready_only_after_scope_and_bot_verification():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=[
            FakeResponse(
                {
                    "code": 0,
                    "data": {
                        "app": {
                            "scopes": [
                                "admin:app.info:readonly",
                                "im:chat:create",
                                "im:chat",
                                "im:message",
                                "im:chat:operate_as_owner",
                            ]
                        }
                    },
                },
                request_id="req-app",
            ),
            FakeResponse(
                {"code": 0, "bot": {"activate_status": 2, "open_id": "ou_bot"}},
                request_id="req-bot",
            ),
        ],
    ) as get:
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is True
    assert result.payload == {"external_request_id": "req-bot"}
    assert get.call_args_list[0].kwargs["params"] == {"lang": "zh_cn"}


def test_connection_exposes_feishu_field_validation_failure():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse(
            {
                "code": 99992402,
                "msg": "field validation failed",
                "error": {
                    "field_violations": [
                        {"field": "lang", "description": "lang is required"}
                    ]
                },
            },
            status_code=400,
            request_id="req-validation",
        ),
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert result.errors[0].field == "lang"
    assert result.errors[0].external_code == "99992402"
    assert result.errors[0].external_request_id == "req-validation"


def test_connection_does_not_require_application_info_permission():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=[
            FakeResponse(
                {
                    "code": 99991672,
                    "msg": "Access denied",
                    "error": {
                        "permission_violations": [
                            {
                                "type": "action_scope_required",
                                "subject": "application:application:self_manage",
                            }
                        ]
                    },
                },
                status_code=400,
                request_id="req-permission",
            ),
            FakeResponse(
                {"code": 0, "bot": {"activate_status": 2, "open_id": "ou_bot"}},
                request_id="req-bot",
            ),
        ],
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is True
    assert result.payload == {
        "external_request_id": "req-bot",
        "permissions_verified": False,
    }


def test_connection_treats_application_server_error_as_retryable():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse({"code": 50001, "msg": "server error"}, status_code=500),
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is True
    assert result.errors[0].code == "provider.request_failed"


def test_connection_treats_bot_rate_limit_as_retryable():
    scopes = [
        "application:application:self_manage",
        "im:chat:create",
        "im:chat",
        "im:message",
        "im:chat:operate_as_owner",
    ]
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=[
            FakeResponse({"code": 0, "data": {"app": {"scopes": scopes}}}),
            FakeResponse({"code": 42901, "msg": "rate limited"}, status_code=429),
        ],
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is True
    assert result.errors[0].code == "provider.request_failed"


@pytest.mark.parametrize(
    ("phase", "invalid_payload"),
    [
        (
            "application",
            requests.exceptions.JSONDecodeError("invalid json", "not-json", 0),
        ),
        ("application", []),
        (
            "bot",
            requests.exceptions.JSONDecodeError("invalid json", "not-json", 0),
        ),
        ("bot", []),
    ],
)
def test_connection_rejects_invalid_json_and_non_object_responses(
    phase,
    invalid_payload,
):
    valid_application = FakeResponse(
        {
            "code": 0,
            "data": {
                "app": {
                    "scopes": [
                        "application:application:self_manage",
                        "im:chat:create",
                        "im:chat",
                        "im:message",
                        "im:chat:operate_as_owner",
                    ]
                }
            },
        }
    )
    invalid_response = FakeResponse(invalid_payload)
    responses = (
        [invalid_response]
        if phase == "application"
        else [valid_application, invalid_response]
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=responses,
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.errors[0].code == "provider.invalid_response"


@pytest.mark.parametrize(
    ("phase", "status_code", "expected_code"),
    [
        ("application", 401, "provider.auth_failed"),
        ("application", 403, "provider.permission_unverified"),
        ("application", 400, "provider.invalid_response"),
        ("application", 404, "provider.invalid_response"),
        ("bot", 401, "provider.auth_failed"),
        ("bot", 403, "provider.auth_failed"),
        ("bot", 400, "provider.invalid_response"),
        ("bot", 404, "provider.invalid_response"),
    ],
)
def test_connection_classifies_non_retryable_http_errors(
    phase,
    status_code,
    expected_code,
):
    valid_application = FakeResponse(
        {
            "code": 0,
            "data": {
                "app": {
                    "scopes": [
                        "application:application:self_manage",
                        "im:chat:create",
                        "im:chat",
                        "im:message",
                        "im:chat:operate_as_owner",
                    ]
                }
            },
        }
    )
    error_response = FakeResponse(
        {"code": status_code, "msg": "request rejected"},
        status_code=status_code,
    )
    responses = (
        [error_response]
        if phase == "application"
        else [valid_application, error_response]
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=responses,
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.errors[0].code == expected_code


@pytest.mark.parametrize(
    ("phase", "invalid_payload"),
    [
        ("application", {"code": 0, "data": ["invalid"]}),
        ("application", {"code": 0, "data": {"app": ["invalid"]}}),
        ("bot", {"code": 0, "bot": ["invalid"]}),
    ],
)
def test_connection_rejects_invalid_nested_response_shapes(
    phase,
    invalid_payload,
):
    valid_application = FakeResponse(
        {
            "code": 0,
            "data": {
                "app": {
                    "scopes": [
                        "application:application:self_manage",
                        "im:chat:create",
                        "im:chat",
                        "im:message",
                        "im:chat:operate_as_owner",
                    ]
                }
            },
        }
    )
    invalid_response = FakeResponse(invalid_payload)
    responses = (
        [invalid_response]
        if phase == "application"
        else [valid_application, invalid_response]
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        side_effect=responses,
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert result.retryable is False
    assert result.errors[0].code == "provider.invalid_response"


def test_create_group_sends_fixed_member_id_type_and_uuid():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
    ) as post:
        result = FeishuIMGroupAdapter.create_group(
            config={"app_id": "app", "app_secret": "secret"},
            provider_key="feishu",
            capability_key="im_group",
            group_name="[INC-1] DB",
            owner_id="ou_owner",
            member_ids=["ou_owner", "ou_user"],
            member_id_type="open_id",
            idempotency_key="bklite-0123456789",
        )

    assert result.success is True
    assert result.payload == {
        "chat_id": "oc_1",
        "invalid_member_ids": [],
        "external_request_id": "req-1",
    }
    request = post.call_args
    assert request.kwargs["params"] == {"user_id_type": "open_id"}
    assert request.kwargs["json"] == {
        "name": "[INC-1] DB",
        "owner_id": "ou_owner",
        "user_id_list": ["ou_owner", "ou_user"],
        "chat_mode": "group",
        "chat_type": "private",
        "set_bot_manager": True,
        "uuid": "bklite-0123456789",
    }
    assert request.kwargs["headers"]["Authorization"] == "Bearer tenant-token"


def test_create_group_returns_invalid_ids_using_same_normalized_payload_as_add_members():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1", "invalid_id_list": ["ou_bad"]}}),
    ):
        result = FeishuIMGroupAdapter.create_group(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            group_name="Incident",
            owner_id="ou_owner",
            member_ids=["ou_owner", "ou_bad"],
            member_id_type="open_id",
            idempotency_key="bklite-create-invalid",
        )

    assert result.success is True
    assert result.partial_success is True
    assert result.payload["invalid_member_ids"] == ["ou_bad"]


def test_add_members_returns_invalid_ids_without_losing_successes():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=FakeResponse({"code": 0, "data": {"invalid_id_list": ["ou_bad"]}}),
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", member_ids=["ou_ok", "ou_bad"], member_id_type="open_id",
        )

    assert result.success is True
    assert result.partial_success is True
    assert result.payload == {"invalid_member_ids": ["ou_bad"], "external_request_id": "req-1"}


def test_get_group_uses_configured_url_and_returns_chat_id():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get", return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
    ) as get:
        result = FeishuIMGroupAdapter.get_group(
            config={"im_group_chat_url": "https://provider.example/chats/{chat_id}"},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
        )

    assert result.success is True
    assert result.payload == {"chat_id": "oc_1", "external_request_id": "req-1"}
    assert get.call_args.args[0] == "https://provider.example/chats/oc_1"


def test_send_group_message_uses_chat_id_receiver_type():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=FakeResponse({"code": 0, "data": {"message_id": "om_1"}}),
    ) as post:
        result = FeishuIMGroupAdapter.send_group_message(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", content="处理已开始", idempotency_key="bklite-summary-0123456789",
        )

    assert result.success is True
    assert result.payload == {"chat_id": "oc_1", "external_request_id": "req-1"}
    assert post.call_args.kwargs["params"] == {"receive_id_type": "chat_id"}
    assert post.call_args.kwargs["json"] == {
        "receive_id": "oc_1",
        "msg_type": "text",
        "content": '{"text": "处理已开始"}',
        "uuid": "bklite-summary-0123456789",
    }


@pytest.mark.parametrize(
    ("response", "expected_code", "retryable"),
    [
        (FakeResponse({"code": 99991663, "msg": "rate limited"}, status_code=429), "provider.request_failed", True),
        (FakeResponse({"code": 99991661, "msg": "permission denied"}, status_code=403), "provider.auth_failed", False),
        (FakeResponse({"code": 99991668, "msg": "not found"}, status_code=404), "provider.group_not_found", False),
        (FakeResponse({"code": 99991663, "msg": "server error"}, status_code=500), "provider.request_failed", True),
    ],
)
def test_group_request_normalizes_provider_errors(response, expected_code, retryable):
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=response
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", member_ids=["ou_user"], member_id_type="open_id",
        )

    assert result.success is False
    assert result.retryable is retryable
    assert result.errors[0].code == expected_code
    assert result.errors[0].external_request_id == "req-1"


def test_group_request_timeout_is_retryable():
    with mock.patch("apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-token", None),), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=requests.Timeout,
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", member_ids=["ou_user"], member_id_type="open_id",
        )

    assert result.success is False
    assert result.retryable is True
    assert result.errors[0].code == "provider.timeout"


def test_group_member_validation_rejects_unsupported_id_type_and_batches_over_fifty(monkeypatch):
    events = []
    monkeypatch.setattr(
        "apps.system_mgmt.providers.adapters.feishu.logger.warning",
        lambda message, *args, **kwargs: events.append(kwargs["extra"]),
    )
    with mock.patch("apps.system_mgmt.providers.adapters.feishu.requests.post") as post:
        invalid_type = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", member_ids=["ou_user"], member_id_type="union_id",
        )
        oversized_batch = FeishuIMGroupAdapter.add_members(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
            member_ids=[f"ou_{index}" for index in range(51)],
            member_id_type="open_id",
        )

    assert invalid_type.errors[0].code == "provider.invalid_config"
    assert invalid_type.errors[0].field == "member_id_type"
    assert oversized_batch.errors[0].code == "provider.invalid_config"
    assert oversized_batch.errors[0].field == "member_ids"
    post.assert_not_called()
    assert [event["operation"] for event in events] == ["add_members", "add_members"]
    assert [event["member_count"] for event in events] == [1, 51]
    assert all(
        event["result"] == "failed"
        and event["error_code"] == "provider.invalid_config"
        and event["request_id"] == ""
        and event["retryable"] is False
        and event["duration_ms"] >= 0
        for event in events
    )


def test_group_request_logs_no_authorization_header(caplog):
    endpoint = "https://provider.example/chats/oc_sensitive?member_id_type=open_id"
    with caplog.at_level(logging.INFO), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-secret-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
    ):
        FeishuIMGroupAdapter.create_group(
            config={"im_group_create_chat_url": endpoint},
            provider_key="feishu",
            capability_key="im_group",
            group_name="DB",
            owner_id="ou_owner",
            member_ids=["ou_owner"],
            member_id_type="open_id",
            idempotency_key="bklite-0123456789",
        )

    assert "Authorization" not in caplog.text
    assert "tenant-secret-token" not in caplog.text
    assert endpoint not in caplog.text
    assert "open_id" not in caplog.text
    assert "status=200" not in caplog.text
    assert "stage=group_request" in caplog.text
    assert "error_code=ok" in caplog.text
    assert "request_id=req-1" in caplog.text
    assert "member_count=1" in caplog.text


def test_group_request_exception_logs_only_whitelisted_fields(caplog):
    exception_text = "request failed at https://provider.example/chats/oc_secret?token=secret"
    with caplog.at_level(logging.WARNING), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token", return_value=("tenant-secret-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post", side_effect=requests.RequestException(exception_text),
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={}, provider_key="feishu", capability_key="im_group", chat_id="oc_1", member_ids=["ou_user"], member_id_type="open_id",
        )

    assert result.success is False
    assert exception_text not in caplog.text
    assert "tenant-secret-token" not in caplog.text
    assert "open_id" not in caplog.text
    assert "stage=group_request" in caplog.text
    assert "error_code=provider.request_failed" in caplog.text
    assert "request_id=" in caplog.text
    assert "member_count=1" in caplog.text


def test_group_request_emits_safe_structured_observability_fields(monkeypatch):
    events = []
    monkeypatch.setattr(
        "apps.system_mgmt.providers.adapters.feishu.time.monotonic",
        mock.Mock(side_effect=[10.0, 10.125]),
    )
    monkeypatch.setattr(
        "apps.system_mgmt.providers.adapters.feishu.logger.info",
        lambda message, *args, **kwargs: events.append((message, kwargs.get("extra"))),
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-secret", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse(
            {"code": 0, "data": {"chat_id": "oc_secret"}},
            request_id="req-safe",
        ),
    ):
        result = FeishuIMGroupAdapter.create_group(
            config={"app_secret": "do-not-log"},
            provider_key="feishu",
            capability_key="im_group",
            group_name="secret title",
            owner_id="ou_secret_owner",
            member_ids=["ou_secret_owner", "ou_secret_member"],
            member_id_type="open_id",
            idempotency_key="secret-idempotency-key",
        )

    assert result.success is True
    assert [extra for _, extra in events] == [
        {
            "event": "feishu_im_group_provider_request",
            "operation": "create_group",
            "duration_ms": 125,
            "result": "success",
            "error_code": "ok",
            "request_id": "req-safe",
            "member_count": 2,
            "retryable": False,
        }
    ]
    rendered = repr(events)
    for secret in (
        "tenant-secret",
        "do-not-log",
        "oc_secret",
        "ou_secret",
        "secret title",
        "secret-idempotency-key",
    ):
        assert secret not in rendered


def test_group_request_sanitizes_untrusted_response_request_id_in_message_and_extra(caplog):
    forged_request_id = "ok\r\nforged="
    with caplog.at_level(logging.INFO), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        side_effect=[
            FakeResponse(
                {"code": 0, "data": {"invalid_id_list": []}},
                request_id=forged_request_id,
            ),
            FakeResponse(
                {"code": 0, "data": {"invalid_id_list": []}},
                request_id="req-searchable-123",
            ),
            FakeResponse(
                {"code": 0, "data": {"invalid_id_list": []}},
                request_id="req-" + ("x" * 500),
            ),
        ],
    ):
        for member_id in ("ou_first", "ou_second", "ou_third"):
            result = FeishuIMGroupAdapter.add_members(
                config={},
                provider_key="feishu",
                capability_key="im_group",
                chat_id="oc_1",
                member_ids=[member_id],
                member_id_type="open_id",
            )
            assert result.success is True

    records = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "feishu_im_group_provider_request"
    ]
    assert len(records) == 3
    forged_message = records[0].getMessage()
    forged_extra = records[0].request_id
    for rendered in (forged_message, forged_extra):
        assert "\r" not in rendered
        assert "\n" not in rendered
        assert "ok\\r\\nforged=" in rendered
    assert records[1].request_id == "req-searchable-123"
    assert "request_id=req-searchable-123" in records[1].getMessage()
    assert len(records[2].request_id) == 200
    assert "\r" not in records[2].request_id
    assert "\n" not in records[2].request_id
    assert ("x" * 201) not in records[2].getMessage()


def test_group_request_logging_failure_does_not_change_provider_result(monkeypatch):
    monkeypatch.setattr(
        "apps.system_mgmt.providers.adapters.feishu.logger.warning",
        mock.Mock(side_effect=RuntimeError("logger unavailable")),
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        side_effect=requests.Timeout,
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_secret",
            member_ids=["ou_secret"],
            member_id_type="open_id",
        )

    assert result.success is False
    assert result.retryable is True
    assert result.errors[0].code == "provider.timeout"


def test_readiness_permission_failure_emits_structured_result(monkeypatch):
    events = []
    monkeypatch.setattr(
        "apps.system_mgmt.providers.adapters.feishu.logger.warning",
        lambda message, *args, **kwargs: events.append(kwargs.get("extra")),
    )
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse(
            {
                "code": 0,
                "data": {
                    "app": {
                        "scopes": ["application:application:self_manage"],
                    }
                },
            },
            request_id="req-permission",
        ),
    ):
        result = FeishuIMGroupAdapter.test_connection(
            config={},
            provider_key="feishu",
            capability_key="im_group",
        )

    assert result.success is False
    assert events == [
        {
            "event": "feishu_im_group_provider_request",
            "operation": "test_connection",
            "duration_ms": mock.ANY,
            "result": "failed",
            "error_code": "provider.permission_unverified",
            "request_id": "req-permission",
            "member_count": 0,
            "retryable": False,
        }
    ]
    assert events[0]["duration_ms"] >= 0
