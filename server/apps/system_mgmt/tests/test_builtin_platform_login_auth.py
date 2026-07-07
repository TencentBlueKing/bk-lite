import pytest
from unittest.mock import patch

from apps.system_mgmt.models import (
    IntegrationInstance,
    IntegrationInstanceStatusChoices,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    LoginModule,
    User,
)
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult


def create_builtin_platform_login_auth():
    instance = IntegrationInstance.objects.create(
        name="BK-Lite 账号体系（平台内建）",
        provider_key="bk_lite_builtin",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
        description="系统内建平台账号体系实例",
    )
    binding = LoginAuthBinding.objects.create(
        name="平台账号密码登录",
        integration_instance=instance,
        description="系统内建平台账号密码登录方式",
        order=0,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )
    return instance, binding


@pytest.mark.django_db
def test_create_builtin_platform_login_auth_creates_builtin_instance_and_binding():
    instance, binding = create_builtin_platform_login_auth()

    assert instance.provider_key == "bk_lite_builtin"
    assert instance.enabled is True
    assert instance.status == IntegrationInstanceStatusChoices.READY
    assert instance.capability_status == {"login_auth": IntegrationInstanceStatusChoices.READY}

    assert binding.integration_instance_id == instance.id
    assert binding.enabled is True
    assert binding.external_field == "username"
    assert binding.platform_field == LoginAuthBindingPlatformFieldChoices.USERNAME
    assert binding.unmatched_user_action == LoginAuthBindingUnmatchedActionChoices.DENY

    assert IntegrationInstance.objects.filter(provider_key="bk_lite_builtin").count() == 1
    assert LoginAuthBinding.objects.filter(integration_instance=instance).count() == 1


@pytest.mark.django_db
def test_init_login_settings_command_creates_builtin_instance_and_binding():
    from django.core.management import call_command

    call_command("init_login_settings")

    assert IntegrationInstance.objects.filter(provider_key="bk_lite_builtin").count() == 1
    assert LoginAuthBinding.objects.filter(integration_instance__provider_key="bk_lite_builtin").count() == 1


@pytest.mark.django_db
def test_init_login_settings_command_normalizes_login_auth_binding_orders():
    from django.core.management import call_command

    builtin_instance, builtin_binding = create_builtin_platform_login_auth()
    secondary_instance = IntegrationInstance.objects.create(
        name="secondary-instance",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    secondary_binding = LoginAuthBinding.objects.create(
        name="secondary-binding",
        integration_instance=secondary_instance,
        description="secondary",
        order=2,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )

    call_command("init_login_settings")

    builtin_binding.refresh_from_db()
    secondary_binding.refresh_from_db()
    assert builtin_binding.order == 1
    assert secondary_binding.order == 2
    ordered_ids = list(LoginAuthBinding.objects.order_by("order", "id").values_list("id", flat=True))
    assert ordered_ids == [builtin_binding.id, secondary_binding.id]


@pytest.mark.django_db
def test_builtin_integration_instance_cannot_be_updated(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"integration_center-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])
    instance, _ = create_builtin_platform_login_auth()

    response = api_client.put(
        f"/api/v1/system_mgmt/integration_instance/{instance.id}/",
        {
            "name": "renamed-instance",
            "provider_key": instance.provider_key,
            "config": instance.config,
            "status": instance.status,
            "capability_status": instance.capability_status,
            "enabled": True,
            "description": instance.description,
            "team": instance.team,
        },
        format="json",
    )

    assert response.status_code == 403
    instance.refresh_from_db()
    assert instance.name != "renamed-instance"


@pytest.mark.django_db
def test_builtin_integration_instance_cannot_be_deleted(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"integration_center-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])
    instance, _ = create_builtin_platform_login_auth()

    response = api_client.delete(f"/api/v1/system_mgmt/integration_instance/{instance.id}/")

    assert response.status_code == 403
    assert IntegrationInstance.objects.filter(id=instance.id).exists() is True


@pytest.mark.django_db
def test_integration_instance_list_filters_out_builtin_instance(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"integration_center-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    builtin_instance, _ = create_builtin_platform_login_auth()
    regular_instance = IntegrationInstance.objects.create(
        name="regular-instance",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )

    response = api_client.get("/api/v1/system_mgmt/integration_instance/")

    assert response.status_code == 200
    payload = response.data["results"] if isinstance(response.data, dict) else response.data
    returned_ids = {item["id"] for item in payload}
    assert regular_instance.id in returned_ids
    assert builtin_instance.id not in returned_ids


@pytest.mark.django_db
def test_builtin_login_auth_binding_allows_display_field_updates(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])
    _, binding = create_builtin_platform_login_auth()

    response = api_client.put(
        f"/api/v1/system_mgmt/login_auth_binding/{binding.id}/",
        {
            "name": "Platform Login",
            "integration_instance": binding.integration_instance_id,
            "icon": "lock",
            "description": "display only update",
            "order": 8,
            "enabled": True,
            "external_field": binding.external_field,
            "platform_field": binding.platform_field,
            "unmatched_user_action": binding.unmatched_user_action,
            "default_group_name": binding.default_group_name,
        },
        format="json",
    )

    assert response.status_code == 200
    binding.refresh_from_db()
    assert binding.name == "Platform Login"
    assert binding.icon == "lock"
    assert binding.description == "display only update"
    assert binding.order == 8


@pytest.mark.django_db
def test_builtin_login_auth_binding_cannot_be_disabled_or_rebound(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Edit"}}
    authenticated_user.save(update_fields=["is_superuser"])
    _, binding = create_builtin_platform_login_auth()
    replacement_instance = IntegrationInstance.objects.create(
        name="replacement",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )

    disable_response = api_client.put(
        f"/api/v1/system_mgmt/login_auth_binding/{binding.id}/",
        {
            "name": binding.name,
            "integration_instance": binding.integration_instance_id,
            "icon": binding.icon,
            "description": binding.description,
            "order": binding.order,
            "enabled": False,
            "external_field": binding.external_field,
            "platform_field": binding.platform_field,
            "unmatched_user_action": binding.unmatched_user_action,
            "default_group_name": binding.default_group_name,
        },
        format="json",
    )

    switch_response = api_client.put(
        f"/api/v1/system_mgmt/login_auth_binding/{binding.id}/",
        {
            "name": binding.name,
            "integration_instance": replacement_instance.id,
            "icon": binding.icon,
            "description": binding.description,
            "order": binding.order,
            "enabled": True,
            "external_field": binding.external_field,
            "platform_field": binding.platform_field,
            "unmatched_user_action": binding.unmatched_user_action,
            "default_group_name": binding.default_group_name,
        },
        format="json",
    )

    assert disable_response.status_code == 400
    assert switch_response.status_code == 400
    binding.refresh_from_db()
    assert binding.enabled is True
    assert binding.integration_instance_id != replacement_instance.id


@pytest.mark.django_db
def test_builtin_login_auth_binding_cannot_be_deleted(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-Delete"}}
    authenticated_user.save(update_fields=["is_superuser"])
    _, binding = create_builtin_platform_login_auth()

    response = api_client.delete(f"/api/v1/system_mgmt/login_auth_binding/{binding.id}/")

    assert response.status_code == 403
    assert LoginAuthBinding.objects.filter(id=binding.id).exists() is True


@pytest.mark.django_db
def test_builtin_integration_instance_excluded_from_available_instances(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"integration_center-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    create_builtin_platform_login_auth()

    response = api_client.get("/api/v1/system_mgmt/integration_instance/available_instances/?capability=login_auth")

    assert response.status_code == 200
    assert not any(item["provider_key"] == "bk_lite_builtin" for item in response.data)


@pytest.mark.django_db
def test_login_auth_binding_list_returns_items_in_order_sequence(api_client, authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.permission = {"system-manager": {"login_auth-View"}}
    authenticated_user.save(update_fields=["is_superuser"])
    first_instance = IntegrationInstance.objects.create(
        name="first-instance",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    second_instance = IntegrationInstance.objects.create(
        name="second-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    first_binding = LoginAuthBinding.objects.create(
        name="first-binding",
        integration_instance=first_instance,
        description="first",
        order=1,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )
    second_binding = LoginAuthBinding.objects.create(
        name="second-binding",
        integration_instance=second_instance,
        description="second",
        order=2,
        enabled=True,
        external_field="username",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )

    response = api_client.get("/api/v1/system_mgmt/login_auth_binding/?page=1&page_size=10")

    assert response.status_code == 200
    assert [item["id"] for item in response.data["items"]] == [first_binding.id, second_binding.id]


@pytest.mark.django_db
def test_get_login_auth_bindings_returns_builtin_binding_public_payload():
    instance, binding = create_builtin_platform_login_auth()

    from apps.system_mgmt.nats_api import get_login_auth_bindings

    response = get_login_auth_bindings()

    assert response["result"] is True
    assert response["data"] == [
        {
            "id": binding.id,
            "name": binding.name,
            "icon": binding.icon,
            "description": binding.description,
            "order": binding.order,
            "provider_key": "bk_lite_builtin",
            "integration_instance_id": instance.id,
            "integration_instance_name": instance.name,
        }
    ]


@pytest.mark.django_db
def test_get_login_auth_bindings_returns_enabled_ready_items_in_order():
    builtin_instance, builtin_binding = create_builtin_platform_login_auth()
    builtin_binding.order = 20
    builtin_binding.save(update_fields=["order"])

    ready_instance = IntegrationInstance.objects.create(
        name="Feishu Ready",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    ready_binding = LoginAuthBinding.objects.create(
        name="Feishu Login",
        integration_instance=ready_instance,
        description="Feishu SSO",
        order=10,
        enabled=True,
        icon="feishu",
        external_field="open_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.DENY,
        default_group_name="",
    )

    from apps.system_mgmt.nats_api import get_login_auth_bindings

    response = get_login_auth_bindings()

    assert response["result"] is True
    assert [item["id"] for item in response["data"]] == [ready_binding.id, builtin_binding.id]
    assert [item["provider_key"] for item in response["data"]] == ["feishu", "bk_lite_builtin"]
    assert [item["order"] for item in response["data"]] == [10, 20]


@pytest.mark.django_db
def test_get_login_auth_bindings_returns_existing_wechat_binding_only():
    instance = IntegrationInstance.objects.create(
        name="微信开放平台",
        provider_key="wechat",
        config={"app_id": "wx-app-id", "app_secret": "wx-app-secret"},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="微信登录",
        integration_instance=instance,
        enabled=True,
        external_field="open_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsPilotGuest",
    )

    from apps.system_mgmt.nats_api import get_login_auth_bindings

    response = get_login_auth_bindings()

    assert response["result"] is True
    assert any(item["id"] == binding.id and item["provider_key"] == "wechat" for item in response["data"])
    assert IntegrationInstance.objects.filter(provider_key="wechat").count() == 1
    assert LoginAuthBinding.objects.filter(integration_instance=instance).count() == 1


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_login_with_binding_resolves_external_user_for_wechat_via_unionid(mock_execute, mock_get_token):
    """unionid 作为 external_field 时,匹配 username=unionid 的已有用户,不会创建 username=openid 用户。"""
    from apps.system_mgmt.services.login_auth_binding_service import login_with_binding

    instance = IntegrationInstance.objects.create(
        name="wechat-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="wechat-binding",
        integration_instance=instance,
        enabled=True,
        external_field="unionid",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsPilotGuest",
    )
    existing = User.objects.create(
        username="uxxx",
        display_name="已存在",
        email="existing@example.com",
    )
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "wechat login authenticated",
        payload={
            "external_user": {
                "openid": "oxxx",
                "unionid": "uxxx",
                "nickname": "Alice",
                "headimgurl": "",
            }
        },
    )
    mock_get_token.return_value = {
        "result": True,
        "data": {"token": "T", "id": existing.id, "username": "uxxx", "display_name": "已存在"},
    }

    result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    # 命中 username="uxxx" 的已有用户
    assert User.objects.filter(username="uxxx").count() == 1
    # 不应创建 username="oxxx" 的新用户
    assert not User.objects.filter(username="oxxx").exists()
    # 已有用户 display_name 不被覆盖
    existing.refresh_from_db()
    assert existing.display_name == "已存在"


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_login_with_binding_resolves_external_user_for_wechat(mock_execute, mock_get_token):
    from apps.system_mgmt.services.login_auth_binding_service import login_with_binding

    instance = IntegrationInstance.objects.create(
        name="wechat-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="wechat-binding",
        integration_instance=instance,
        description="wechat",
        order=1,
        enabled=True,
        external_field="openid",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsPilotGuest",
    )
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "wechat login authenticated",
        payload={
            "external_user": {
                "openid": "oxxx-matched",
                "unionid": "uxxx",
                "nickname": "Alice",
                "headimgurl": "",
            }
        },
    )
    existing = User.objects.create(
        username="oxxx-matched",
        display_name="旧显示名",
        email="old@example.com",
        phone="13800000000",
    )
    mock_get_token.return_value = {
        "result": True,
        "data": {"token": "T", "id": existing.id, "username": existing.username, "display_name": "旧显示名"},
    }

    result = login_with_binding(binding.id, "auth-code")

    # 匹配到已有用户,只刷 last_login,不修改 display_name / email / phone
    existing.refresh_from_db()
    assert existing.display_name == "旧显示名"
    assert existing.email == "old@example.com"
    assert existing.phone == "13800000000"
    assert result["result"] is True
    assert result["data"]["token"] == "T"
    mock_get_token.assert_called_once()


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_login_with_binding_creates_new_user_with_nickname_for_wechat(mock_execute, mock_get_token):
    from apps.system_mgmt.services.login_auth_binding_service import login_with_binding

    instance = IntegrationInstance.objects.create(
        name="wechat-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="wechat-binding",
        integration_instance=instance,
        enabled=True,
        external_field="openid",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsPilotGuest",
    )
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "wechat login authenticated",
        payload={
            "external_user": {
                "openid": "oxxx-new",
                "unionid": "",
                "nickname": "新昵称",
                "headimgurl": "",
            }
        },
    )
    mock_get_token.return_value = {
        "result": True,
        "data": {"token": "T", "id": 1, "username": "oxxx-new", "display_name": "新昵称"},
    }

    result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    new_user = User.objects.get(username="oxxx-new")
    assert new_user.display_name == "新昵称"


@pytest.mark.django_db
@patch("apps.system_mgmt.nats.login.get_user_login_token")
@patch("apps.system_mgmt.services.login_auth_binding_service.RuntimeApplicationService.execute")
def test_login_with_binding_falls_back_to_ops_pilot_guest_for_wechat(mock_execute, mock_get_token):
    from apps.system_mgmt.models import Group
    from apps.system_mgmt.services.login_auth_binding_service import login_with_binding

    instance = IntegrationInstance.objects.create(
        name="wechat-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="wechat-binding",
        integration_instance=instance,
        enabled=True,
        external_field="openid",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="",  # 后端 fallback 到 OpsPilotGuest
    )
    mock_execute.return_value = CapabilityExecutionResult.success_result(
        "wechat login authenticated",
        payload={
            "external_user": {
                "openid": "oxxx-fallback",
                "unionid": "",
                "nickname": "游客",
                "headimgurl": "",
            }
        },
    )
    mock_get_token.return_value = {
        "result": True,
        "data": {"token": "T", "id": 1, "username": "oxxx-fallback", "display_name": "游客"},
    }

    result = login_with_binding(binding.id, "auth-code")

    assert result["result"] is True
    new_user = User.objects.get(username="oxxx-fallback")
    guest_group = Group.objects.get(name="OpsPilotGuest", parent_id=0)
    assert guest_group.id in new_user.group_list


@pytest.mark.django_db
def test_serializer_allows_wechat_create_with_empty_default_group():
    """WeChat + create + 空 default_group_name 允许通过(后端 fallback 到 OpsPilotGuest)。"""
    from apps.system_mgmt.serializers.login_auth_binding_serializer import LoginAuthBindingSerializer

    instance = IntegrationInstance.objects.create(
        name="wechat-instance",
        provider_key="wechat",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    serializer = LoginAuthBindingSerializer(data={
        "name": "微信登录",
        "integration_instance": instance.id,
        "external_field": "openid",
        "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
        "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
        "default_group_name": "",
        "enabled": True,
    })
    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_non_wechat_create_with_empty_default_group():
    """非 WeChat + create + 空 default_group_name 仍要求必填。"""
    from apps.system_mgmt.serializers.login_auth_binding_serializer import LoginAuthBindingSerializer

    instance = IntegrationInstance.objects.create(
        name="feishu-instance",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    serializer = LoginAuthBindingSerializer(data={
        "name": "飞书登录",
        "integration_instance": instance.id,
        "external_field": "user_id",
        "platform_field": LoginAuthBindingPlatformFieldChoices.USERNAME,
        "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
        "default_group_name": "",
        "enabled": True,
    })
    assert not serializer.is_valid()
    assert "default_group_name" in serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_non_wechat_update_clearing_default_group():
    """非 WeChat create binding 在 update 场景显式提交 default_group_name="" 必须被拒绝。

    旧实现的 `attrs.get(...) or getattr(...)` 会把显式空字符串误回退为旧值,
    让空值通过校验但仍以 "" 持久化,违反 spec。修复后用 `in` 区分未提交和显式空。
    """
    from apps.system_mgmt.serializers.login_auth_binding_serializer import LoginAuthBindingSerializer

    instance = IntegrationInstance.objects.create(
        name="feishu-instance",
        provider_key="feishu",
        config={},
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={"login_auth": IntegrationInstanceStatusChoices.READY},
        enabled=True,
    )
    binding = LoginAuthBinding.objects.create(
        name="feishu-binding",
        integration_instance=instance,
        enabled=True,
        external_field="user_id",
        platform_field=LoginAuthBindingPlatformFieldChoices.USERNAME,
        unmatched_user_action=LoginAuthBindingUnmatchedActionChoices.CREATE,
        default_group_name="OpsGuests",
    )
    serializer = LoginAuthBindingSerializer(
        binding,
        data={
            "name": binding.name,
            "integration_instance": instance.id,
            "external_field": binding.external_field,
            "platform_field": binding.platform_field,
            "unmatched_user_action": LoginAuthBindingUnmatchedActionChoices.CREATE,
            "default_group_name": "",  # 显式清空,非 WeChat 应被拒绝
            "enabled": binding.enabled,
        },
        partial=True,
    )
    assert not serializer.is_valid(), serializer.errors
    assert "default_group_name" in serializer.errors
