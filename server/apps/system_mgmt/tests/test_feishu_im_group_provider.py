import logging
from unittest import mock

import pytest
import requests

from apps.system_mgmt.providers.adapters.feishu import FeishuIMGroupAdapter
from apps.system_mgmt.providers.manifests.feishu import PROVIDER_MANIFEST


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
    assert {field.key for field in capability.connection_template} == {
        "im_group_create_chat_url",
        "im_group_chat_url",
        "im_group_members_url",
        "im_group_send_message_url",
    }


def test_create_group_sends_fixed_member_id_type_and_uuid():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
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
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse(
            {"code": 0, "data": {"chat_id": "oc_1", "invalid_id_list": ["ou_bad"]}}
        ),
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
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"invalid_id_list": ["ou_bad"]}}),
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
            member_ids=["ou_ok", "ou_bad"],
            member_id_type="open_id",
        )

    assert result.success is True
    assert result.partial_success is True
    assert result.payload == {"invalid_member_ids": ["ou_bad"], "external_request_id": "req-1"}


def test_get_group_uses_configured_url_and_returns_chat_id():
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.get",
        return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
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
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"message_id": "om_1"}}),
    ) as post:
        result = FeishuIMGroupAdapter.send_group_message(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
            content="处理已开始",
            idempotency_key="bklite-summary-0123456789",
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
    with mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-token", None),
    ), mock.patch("apps.system_mgmt.providers.adapters.feishu.requests.post", return_value=response):
        result = FeishuIMGroupAdapter.add_members(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
            member_ids=["ou_user"],
            member_id_type="open_id",
        )

    assert result.success is False
    assert result.retryable is retryable
    assert result.errors[0].code == expected_code
    assert result.errors[0].external_request_id == "req-1"


def test_group_request_timeout_is_retryable():
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
            chat_id="oc_1",
            member_ids=["ou_user"],
            member_id_type="open_id",
        )

    assert result.success is False
    assert result.retryable is True
    assert result.errors[0].code == "provider.timeout"


def test_group_member_validation_rejects_unsupported_id_type_and_batches_over_fifty():
    invalid_type = FeishuIMGroupAdapter.add_members(
        config={},
        provider_key="feishu",
        capability_key="im_group",
        chat_id="oc_1",
        member_ids=["ou_user"],
        member_id_type="union_id",
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


def test_group_request_logs_no_authorization_header(caplog):
    endpoint = "https://provider.example/chats/oc_sensitive?member_id_type=open_id"
    with caplog.at_level(logging.INFO), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-secret-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        return_value=FakeResponse({"code": 0, "data": {"chat_id": "oc_1"}}),
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
        "apps.system_mgmt.providers.adapters.feishu._fetch_tenant_access_token",
        return_value=("tenant-secret-token", None),
    ), mock.patch(
        "apps.system_mgmt.providers.adapters.feishu.requests.post",
        side_effect=requests.RequestException(exception_text),
    ):
        result = FeishuIMGroupAdapter.add_members(
            config={},
            provider_key="feishu",
            capability_key="im_group",
            chat_id="oc_1",
            member_ids=["ou_user"],
            member_id_type="open_id",
        )

    assert result.success is False
    assert exception_text not in caplog.text
    assert "tenant-secret-token" not in caplog.text
    assert "open_id" not in caplog.text
    assert "stage=group_request" in caplog.text
    assert "error_code=provider.request_failed" in caplog.text
    assert "request_id=" in caplog.text
    assert "member_count=1" in caplog.text
