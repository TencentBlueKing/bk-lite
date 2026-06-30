from urllib.parse import urlencode

from django.contrib.auth.hashers import make_password
from django.utils import timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import (
    Group,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    User,
)
from apps.system_mgmt.providers import RuntimeApplicationService


def get_active_login_auth_bindings():
    bindings = []
    queryset = LoginAuthBinding.objects.select_related("integration_instance").filter(enabled=True).order_by("order", "id")
    for binding in queryset:
        instance = binding.integration_instance
        if not instance.enabled:
            continue
        if instance.capability_status.get("login_auth") != "ready":
            continue
        bindings.append(binding)
    return bindings


def build_login_auth_redirect(binding: LoginAuthBinding, redirect_uri: str, state: str = ""):
    runtime_service = RuntimeApplicationService()
    instance = binding.integration_instance
    result = runtime_service.execute(
        provider_key=instance.provider_key,
        capability_key="login_auth",
        operation="build_login_url",
        config=instance.get_runtime_config(),
        binding=binding,
        redirect_uri=redirect_uri,
        state=state,
    )
    return result


def login_with_binding(binding_id: int, auth_code: str = "", *, username: str = "", password: str = ""):
    from apps.system_mgmt.nats_api import get_user_login_token

    binding = (
        LoginAuthBinding.objects.select_related("integration_instance")
        .filter(id=binding_id, enabled=True)
        .first()
    )
    if not binding:
        return {"result": False, "message": "Login auth binding not found"}

    instance = binding.integration_instance
    if not instance.enabled or instance.capability_status.get("login_auth") != "ready":
        return {"result": False, "message": "Login auth binding is not ready"}

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=instance.provider_key,
        capability_key="login_auth",
        operation="authenticate",
        config=instance.get_runtime_config(),
        binding=binding,
        auth_code=auth_code,
        username=username,
        password=password,
    )
    if not result.success:
        return {"result": False, "message": result.summary, "data": result.to_dict()}

    adapter_login_result = result.payload.get("login_result") or {}
    if adapter_login_result:
        return {"result": True, "data": adapter_login_result}

    external_user = result.payload.get("external_user") or {}
    user = _resolve_platform_user(binding, external_user)
    if not user:
        return {"result": False, "message": "No matching platform user found"}

    user.last_login = timezone.now()
    user.save(update_fields=["last_login", "updated_at"] if hasattr(user, "updated_at") else ["last_login"])
    token_result = get_user_login_token(user, user.username, skip_token_for_otp=True)
    if token_result.get("result"):
        token_result["data"]["domain"] = "domain.com"
    return token_result


def _resolve_platform_user(binding: LoginAuthBinding, external_user: dict):
    platform_field = binding.platform_field
    external_value = external_user.get(binding.external_field) or external_user.get("user_id") or external_user.get("open_id") or ""
    if not external_value:
        return None

    filter_kwargs = {platform_field: external_value}
    user = User.objects.filter(**filter_kwargs).first()
    if user:
        return _update_user_profile(user, external_user)

    if binding.unmatched_user_action != LoginAuthBindingUnmatchedActionChoices.CREATE:
        return None

    default_group = None
    if binding.default_group_name:
        default_group, _ = Group.objects.get_or_create(name=binding.default_group_name, parent_id=0)

    username = external_user.get("user_id") or external_user.get("open_id") or external_user.get("email") or external_value
    email = external_user.get("email", "")
    phone = external_user.get("mobile", "")
    display_name = external_user.get("name") or username
    user = User.objects.create(
        username=username,
        display_name=display_name,
        email=email,
        phone=phone,
        password=make_password(""),
        domain="domain.com",
        group_list=[default_group.id] if default_group else [],
    )
    logger.info(f"Created platform user '{username}' from login auth binding '{binding.name}'")
    return user


def _update_user_profile(user: User, external_user: dict):
    updated = False
    if external_user.get("name") and user.display_name != external_user["name"]:
        user.display_name = external_user["name"]
        updated = True
    if external_user.get("email") and user.email != external_user["email"]:
        user.email = external_user["email"]
        updated = True
    if external_user.get("mobile") and getattr(user, "phone", "") != external_user["mobile"]:
        user.phone = external_user["mobile"]
        updated = True
    if updated:
        user.save()
    return user


def serialize_public_login_auth_binding(binding: LoginAuthBinding):
    instance = binding.integration_instance
    return {
        "id": binding.id,
        "name": binding.name,
        "icon": binding.icon,
        "description": binding.description,
        "order": binding.order,
        "provider_key": instance.provider_key,
        "integration_instance_id": instance.id,
        "integration_instance_name": instance.name,
    }


def build_state_payload(binding_id: int, redirect_uri: str):
    return urlencode({"binding_id": binding_id, "redirect_uri": redirect_uri})
