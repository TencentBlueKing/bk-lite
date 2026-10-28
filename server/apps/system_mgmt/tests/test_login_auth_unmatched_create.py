import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from apps.system_mgmt.models import (
    Group,
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    Role,
    User,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.login_auth_binding_service import login_with_binding

_PROFILE_ENRICH_TEMPLATE = "event=login_auth_profile_enrich_failed binding_id=%s provider_key=%s failed_stage=%s error_type=%s"
_SECRET = "profile-token-sentinel-SECRET"
_BODY = "must-not-log-profile-body"


def _ready_instance(provider_key, name, config):
    return IntegrationInstance.objects.create(
        name=name,
        provider_key=provider_key,
        config=config,
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )


def _binding(instance, **overrides):
    values = {
        "name": f"{instance.provider_key} login",
        "integration_instance": instance,
        "enabled": True,
        "external_field": "userid" if instance.provider_key == "wecom" else "username",
        "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
        "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
        "default_group_name": "",
    }
    values.update(overrides)
    return LoginAuthBinding.objects.create(**values)


def _json_response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _token_result(username, display_name):
    return {"result": True, "data": {"token": "T", "id": 1, "username": username, "display_name": display_name}}


def _assert_profile_warning(caplog, binding_id, provider_key, error_type, error=None):
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    record = warnings[0]
    assert record.msg == _PROFILE_ENRICH_TEMPLATE
    assert record.args == (binding_id, provider_key, "enrich_profile", error_type)
    formatted = logging.Formatter().format(record)
    blob = "\n".join([record.getMessage(), formatted, caplog.text])
    assert _SECRET not in blob
    assert _BODY not in blob
    assert not any(item.levelno >= logging.ERROR for item in caplog.records)
    if error is None:
        assert record.exc_info is None
        return
    assert record.exc_info[0].__name__ == "SafeLogException"
    assert str(record.exc_info[1]) == type(error).__name__
    assert record.exc_info[2] is error.__traceback__
    assert str(error) == _BODY


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_feishu_create_uses_login_name_and_ops_pilot_guest_without_another_request(mock_execute, mock_get_token):
    instance = _ready_instance("feishu", "Feishu", {})
    binding = _binding(instance, external_field="user_id")
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"user_id": "ou_alice", "name": "爱丽丝", "email": "alice@example.com", "mobile": "13800000000"}},
    )
    mock_get_token.return_value = _token_result("ou_alice", "爱丽丝")
    Role.objects.create(name="normal", app="ops-console", menu_list=[])
    Role.objects.create(name="normal", app="opspilot", menu_list=[])

    with patch("apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get") as wecom_get, patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get"
    ) as blueking_get:
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    wecom_get.assert_not_called()
    blueking_get.assert_not_called()
    user = User.objects.get(username="ou_alice")
    assert user.display_name == "爱丽丝"
    assert user.email == "alice@example.com"
    assert user.phone == "13800000000"
    guest = Group.objects.get(name="OpsPilotGuest", parent_id=0)
    assert guest.id in user.group_list
    assigned = set(Role.objects.filter(id__in=user.role_list).values_list("name", "app"))
    assert {("normal", "ops-console"), ("normal", "opspilot")} <= assigned


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_wecom_create_reads_member_name_and_joins_ops_pilot_guest(mock_execute, mock_get_token):
    instance = _ready_instance("wecom", "WeCom", {"corp_id": "ww", "corp_secret": _SECRET, "agent_id": "1"})
    binding = _binding(instance)
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"userid": "zhangsan"}},
    )
    mock_get_token.return_value = _token_result("zhangsan", "张三")

    with patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=[
            _json_response({"errcode": 0, "access_token": _SECRET}),
            _json_response({"errcode": 0, "userid": "zhangsan", "name": "张三", "email": "zs@example.com", "mobile": "13900000000"}),
        ],
    ) as get:
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    assert [call.args[0] for call in get.call_args_list] == [
        "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
        "https://qyapi.weixin.qq.com/cgi-bin/user/get",
    ]
    assert get.call_args_list[1].kwargs["params"]["userid"] == "zhangsan"
    user = User.objects.get(username="zhangsan")
    assert user.display_name == "张三"
    assert user.email == "zs@example.com"
    assert user.phone == "13900000000"
    guest = Group.objects.get(name="OpsPilotGuest", parent_id=0)
    assert guest.id in user.group_list


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_wecom_profile_failure_does_not_create_user_and_logs_one_warning(mock_execute, mock_get_token, caplog):
    instance = _ready_instance("wecom", "WeCom", {"corp_id": "ww", "corp_secret": _SECRET, "agent_id": "1"})
    binding = _binding(instance)
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"userid": "zhangsan"}},
    )
    mock_get_token.return_value = _token_result("zhangsan", "zhangsan")

    timeout = requests.Timeout(_BODY)
    with caplog.at_level(logging.DEBUG), patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=timeout,
    ):
        result = login_with_binding(binding.id, "auth-code")

    assert result == {"result": False, "message": "Failed to read the external user profile"}
    assert not User.objects.filter(username="zhangsan").exists()
    _assert_profile_warning(caplog, binding.id, "wecom", "Timeout", timeout)
    assert not any("no matching platform user" in record.getMessage() for record in caplog.records)


@pytest.mark.django_db
@patch("apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get")
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_wecom_does_not_read_member_when_user_exists_or_action_is_deny(mock_execute, mock_get_token, get):
    instance = _ready_instance("wecom", "WeCom", {"corp_id": "ww", "corp_secret": _SECRET, "agent_id": "1"})
    User.objects.create(username="zhangsan", display_name="旧名", password="", domain="domain.com")
    existing = _binding(instance, name="existing")
    denied = _binding(
        instance,
        name="denied",
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
    )
    mock_get_token.return_value = _token_result("zhangsan", "旧名")

    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"userid": "zhangsan"}},
    )
    existing_result = login_with_binding(existing.id, "auth-code")

    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"userid": "lisi"}},
    )
    denied_result = login_with_binding(denied.id, "auth-code")

    assert existing_result["result"] is True
    assert denied_result["result"] is False
    get.assert_not_called()
    assert User.objects.get(username="zhangsan").display_name == "旧名"
    assert not User.objects.filter(username="lisi").exists()


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_blueking_create_reads_display_name_and_joins_saved_group(mock_execute, mock_get_token):
    instance = _ready_instance(
        "blueking",
        "BlueKing",
        {"bk_url": "https://bk.example.com", "app_id": "bk-app", "app_token": _SECRET},
    )
    binding = _binding(instance, external_field="username", default_group_name="Finance")
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"username": "alice"}},
    )
    mock_get_token.return_value = _token_result("alice", "爱丽丝")

    with patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        return_value=_json_response(
            {"result": True, "data": {"username": "alice", "display_name": "爱丽丝", "email": "alice@example.com", "telephone": "13700000000"}}
        ),
    ) as get:
        result = login_with_binding(binding.id, bk_token="bk-token")

    assert result["result"] is True
    assert get.call_args.args[0] == "https://bk.example.com/api/c/compapi/v2/usermanage/retrieve_user/"
    assert get.call_args.kwargs["params"]["id"] == "alice"
    assert get.call_args.kwargs["params"]["bk_username"] == "admin"
    assert "bk_token" not in get.call_args.kwargs["params"]
    user = User.objects.get(username="alice")
    assert user.display_name == "爱丽丝"
    assert user.email == "alice@example.com"
    assert user.phone == "13700000000"
    finance = Group.objects.get(name="Finance", parent_id=0)
    assert user.group_list == [finance.id]


@pytest.mark.django_db
@patch("apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get")
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_blueking_does_not_read_profile_when_user_already_exists(mock_execute, mock_get_token, get):
    instance = _ready_instance(
        "blueking",
        "BlueKing",
        {"bk_url": "https://bk.example.com", "app_id": "bk-app", "app_token": _SECRET},
    )
    User.objects.create(username="alice", display_name="旧名", email="old@example.com", password="", domain="domain.com")
    binding = _binding(instance, external_field="username")
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"username": "alice"}},
    )
    mock_get_token.return_value = _token_result("alice", "旧名")

    result = login_with_binding(binding.id, bk_token="bk-token")

    assert result["result"] is True
    get.assert_not_called()
    user = User.objects.get(username="alice")
    assert user.display_name == "旧名"
    assert user.email == "old@example.com"


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_wecom_blank_name_still_creates_user(mock_execute, mock_get_token, caplog):
    instance = _ready_instance("wecom", "WeCom", {"corp_id": "ww", "corp_secret": _SECRET, "agent_id": "1"})
    binding = _binding(instance)
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"userid": "zhangsan"}},
    )
    mock_get_token.return_value = _token_result("zhangsan", "zhangsan")

    with caplog.at_level(logging.DEBUG), patch(
        "apps.system_mgmt.providers.builtin.wecom.adapters.client.requests.get",
        side_effect=[
            _json_response({"errcode": 0, "access_token": _SECRET}),
            _json_response({"errcode": 0, "userid": "zhangsan", "name": "", "email": "zs@example.com", "mobile": "", "errmsg": _BODY}),
        ],
    ):
        result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    user = User.objects.get(username="zhangsan")
    assert user.display_name == "zhangsan"
    assert user.email == "zs@example.com"
    assert not any(record.msg == _PROFILE_ENRICH_TEMPLATE for record in caplog.records)


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_blueking_profile_failure_does_not_create_user_and_logs_one_warning(mock_execute, mock_get_token, caplog):
    instance = _ready_instance(
        "blueking",
        "BlueKing",
        {"bk_url": "https://bk.example.com", "app_id": "bk-app", "app_token": _SECRET},
    )
    binding = _binding(instance, external_field="username")
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "ok",
        payload={"external_user": {"username": "alice"}},
    )
    mock_get_token.return_value = _token_result("alice", "alice")
    timeout = requests.Timeout(_BODY)

    with caplog.at_level(logging.DEBUG), patch(
        "apps.system_mgmt.providers.builtin.blueking.adapters.client.requests.get",
        side_effect=timeout,
    ):
        result = login_with_binding(binding.id, bk_token="bk-token")

    assert result == {"result": False, "message": "Failed to read the external user profile"}
    assert not User.objects.filter(username="alice").exists()
    _assert_profile_warning(caplog, binding.id, "blueking", "Timeout", timeout)
    assert not any("no matching platform user" in record.getMessage() for record in caplog.records)
