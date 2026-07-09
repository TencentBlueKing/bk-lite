from urllib.parse import urlencode

from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.utils import timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import (
    Group,
    LoginAuthBinding,
    LoginAuthBindingPlatformFieldChoices,
    LoginAuthBindingUnmatchedActionChoices,
    Role,
    User,
)
from apps.system_mgmt.providers import RuntimeApplicationService

# 微信等第三方登陆首次创建用户时,写入与旧 wechat_user_register
# (server/apps/system_mgmt/nats/wechat.py:16-26) 对齐的默认 role 集合。
# 缺 normal@ops-console 会让 verify_token 的菜单汇总为空,opsconsole 在
# get_client 返回中消失,用户看不到入口。
_DEFAULT_PLATFORM_ROLE_QUERY = Q(
    name="normal", app__in=["opspilot", "ops-console"]
) | Q(
    name="guest",
    app__in=[
        "opspilot",
        "cmdb",
        "monitor",
        "log",
        "alarm",
        "node",
        "mlops",
        "job",
    ],
)


def _default_platform_role_ids() -> list:
    return list(
        Role.objects.filter(_DEFAULT_PLATFORM_ROLE_QUERY).values_list("id", flat=True)
    )


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
    from apps.system_mgmt.nats.login import get_user_login_token

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
        # `domain` is a deprecated compatibility field. New login-auth users are
        # intentionally kept in the legacy default domain until the column is removed.
        token_result["data"]["domain"] = "domain.com"
    return token_result


def _resolve_platform_user(binding: LoginAuthBinding, external_user: dict):
    platform_field = binding.platform_field
    external_value = external_user.get(binding.external_field) or external_user.get("openid") or ""
    if not external_value:
        return None

    filter_kwargs = {platform_field: external_value}
    user = User.objects.filter(**filter_kwargs).first()
    if user:
        # 登录认证不修改已有用户资料(display_name / email / phone / group_list / role_list),
        # last_login 由 login_with_binding 外层刷。
        return user

    if binding.unmatched_user_action != LoginAuthBindingUnmatchedActionChoices.CREATE:
        return None

    # 微信登录认证未配置默认组织时,沿用旧微信扫码登录行为,
    # 自动加入 OpsPilotGuest 组,以便进入 ops-console 首页后触发
    # init_user_set 首次登录创建组织弹窗。
    default_group_name = binding.default_group_name
    if not default_group_name and binding.integration_instance.provider_key == "wechat":
        default_group_name = "OpsPilotGuest"

    default_group = None
    if default_group_name:
        default_group, _ = Group.objects.get_or_create(name=default_group_name, parent_id=0)

    provider_key = binding.integration_instance.provider_key
    if provider_key == "wechat":
        username = external_user.get("openid") or external_value
        display_name = external_user.get("nickname") or username
    else:
        username = external_value
        display_name = external_user.get("name") or username
    email = external_user.get("email", "") if platform_field != "email" else external_value
    phone = external_user.get("mobile", "") if platform_field != "phone" else external_value
    user = User.objects.create(
        username=username,
        display_name=display_name,
        email=email,
        phone=phone,
        password=make_password(""),
        # `domain` is retained only for compatibility with legacy user identity
        # code. Do not treat provider integrations as multi-domain sources here.
        domain="domain.com",
        group_list=[default_group.id] if default_group else [],
        # 默认 role 与旧 wechat_user_register 路径(server/apps/system_mgmt/nats/wechat.py)
        # 对齐:normal@ops-console 决定 opsconsole 模块入口可见,guest@* 决定其余模块只读权限。
        role_list=_default_platform_role_ids(),
    )
    logger.info(f"Created platform user '{username}' from login auth binding '{binding.name}'")
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
