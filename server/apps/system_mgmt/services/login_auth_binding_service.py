import uuid
from urllib.parse import urlencode

from django.contrib.auth.hashers import make_password
from django.db.models import Q
from django.utils import timezone

from apps.core.logger import safe_exception_info
from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import Group, LoginAuthBinding, LoginAuthBindingUnmatchedActionChoices, Role, User
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.providers.builtin.blueking.adapters.client import retrieve_user_profile
from apps.system_mgmt.providers.builtin.wecom.adapters.client import fetch_member_profile
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability

# 微信等第三方登陆首次创建用户时,写入与旧 wechat_user_register
# (server/apps/system_mgmt/nats/wechat.py:16-26) 对齐的默认 role 集合。
# 缺 normal@ops-console 会让 verify_token 的菜单汇总为空,opsconsole 在
# get_client 返回中消失,用户看不到入口。
_DEFAULT_PLATFORM_ROLE_QUERY = Q(name="normal", app__in=["opspilot", "ops-console"]) | Q(
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
    return list(Role.objects.filter(_DEFAULT_PLATFORM_ROLE_QUERY).values_list("id", flat=True))


BLUEKING_PROVIDER_KEY = "blueking"
_OPS_PILOT_GUEST_PROVIDERS = {"wechat", "feishu", "wecom", "blueking"}
_PROFILE_ENRICH_TEMPLATE = "event=login_auth_profile_enrich_failed binding_id=%s provider_key=%s failed_stage=%s error_type=%s"
_PROFILE_UNAVAILABLE_MESSAGE = "Failed to read the external user profile"


class _LoginProfileUnavailable(Exception):
    """企微或蓝鲸目录接口失败。登录失败，且不建号。"""


_BLUEKING_PROVIDER_LOGGED_CODES = frozenset(
    {
        "provider.auth_failed",
        "provider.invalid_config",
        "provider.timeout",
        "provider.request_failed",
    }
)


def get_active_login_auth_bindings():
    bindings = []
    queryset = LoginAuthBinding.objects.select_related("integration_instance").filter(enabled=True).order_by("order", "id")
    for binding in queryset:
        instance = binding.integration_instance
        if instance.provider_key == BLUEKING_PROVIDER_KEY:
            continue
        if not get_integration_capability_availability(instance, "login_auth")["available"]:
            continue
        bindings.append(binding)
    return bindings


def get_ready_blueking_login_auth_binding():
    queryset = (
        LoginAuthBinding.objects.select_related("integration_instance")
        .filter(enabled=True, integration_instance__provider_key=BLUEKING_PROVIDER_KEY)
        .order_by("order", "id")
    )
    for binding in queryset:
        if get_integration_capability_availability(binding.integration_instance, "login_auth")["available"]:
            return binding
    return None


def build_login_auth_redirect(binding: LoginAuthBinding, redirect_uri: str, state: str = ""):
    runtime_service = RuntimeApplicationService()
    instance = binding.integration_instance
    if not get_integration_capability_availability(instance, "login_auth")["available"]:
        return CapabilityExecutionResult.failed_result(
            "Login auth binding is not ready",
            code="integration.capability_unavailable",
        )
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


def login_with_binding(binding_id: int, auth_code: str = "", *, username: str = "", password: str = "", bk_token: str = ""):
    from apps.system_mgmt.nats.login import get_user_login_token

    binding = LoginAuthBinding.objects.select_related("integration_instance").filter(id=binding_id, enabled=True).first()
    if not binding:
        logger.warning(f"login_with_binding: binding not found, binding_id={binding_id}")
        return {"result": False, "message": "Login auth binding not found"}

    instance = binding.integration_instance
    if not get_integration_capability_availability(instance, "login_auth")["available"]:
        logger.warning(
            f"login_with_binding: binding not ready, "
            f"binding_id={binding_id}, provider_key={instance.provider_key}, "
            f"instance_enabled={instance.enabled}, "
            f"capability_status={dict(instance.capability_status or {})}"
        )
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
        bk_token=bk_token,
    )
    if not result.success:
        # 外部 API 失败（AD/Feishu/WeChat 拒绝或网络错误），记 ERROR 触发运维告警。
        # 含 provider_key + binding_id + error code + summary + 错误列表，便于区分平台 vs 外部。
        error_codes = [e.code for e in (result.errors or [])]
        provider_already_logged = (
            instance.provider_key == BLUEKING_PROVIDER_KEY and bool(error_codes) and set(error_codes).issubset(_BLUEKING_PROVIDER_LOGGED_CODES)
        )
        if not provider_already_logged:
            logger.error(
                f"login_with_binding: external authenticate failed, "
                f"binding_id={binding_id}, provider_key={instance.provider_key}, "
                f"username={username!r}, summary={result.summary!r}, "
                f"codes={error_codes}, request_id={result.request_id}"
            )
        return {"result": False, "message": result.summary, "data": result.to_dict()}

    adapter_login_result = result.payload.get("login_result") or {}
    if adapter_login_result:
        logger.info(
            f"login_with_binding succeeded via adapter-supplied login_result, " f"binding_id={binding_id}, provider_key={instance.provider_key}"
        )
        return {"result": True, "data": adapter_login_result}

    external_user = result.payload.get("external_user") or {}
    try:
        user = _resolve_platform_user(binding, external_user)
    except _LoginProfileUnavailable:
        return {"result": False, "message": _PROFILE_UNAVAILABLE_MESSAGE}
    if not user:
        # 外部认证成功但本地无匹配：通常是 binding.platform_field / external_field 配置错，
        # 或 sync 任务未跑、用户没建。WARNING 提示运维检查，不告警。
        logger.warning(
            f"login_with_binding: no matching platform user, "
            f"binding_id={binding_id}, provider_key={instance.provider_key}, "
            f"platform_field={binding.platform_field}, "
            f"external_user={dict(external_user)}"
        )
        return {"result": False, "message": "No matching platform user found"}

    user.last_login = timezone.now()
    user.save(update_fields=["last_login", "updated_at"] if hasattr(user, "updated_at") else ["last_login"])
    token_result = get_user_login_token(user, user.username, skip_token_for_otp=True)
    if token_result.get("result"):
        # `domain` is a deprecated compatibility field. New login-auth users are
        # intentionally kept in the legacy default domain until the column is removed.
        token_result["data"]["domain"] = "domain.com"
        logger.info(
            f"login_with_binding succeeded, "
            f"binding_id={binding_id}, provider_key={instance.provider_key}, "
            f"username={user.username}, platform_user_id={user.id}"
        )
    return token_result


def _merge_login_profile(external_user, profile):
    merged = dict(external_user)
    for key in ("name", "email", "mobile"):
        value = str((profile or {}).get(key) or "").strip()
        if value:
            merged[key] = value
    return merged


def _warn_profile_enrich_failed(binding_id, provider_key, error_type, error):
    logger.warning(
        _PROFILE_ENRICH_TEMPLATE,
        binding_id,
        provider_key,
        "enrich_profile",
        error_type,
        exc_info=safe_exception_info(error) if error is not None else None,
    )


def _enrich_external_user_for_create(binding: LoginAuthBinding, external_user: dict):
    """本地无用户且选择创建时，为企微和蓝鲸补姓名。目录接口失败则不建号。"""
    provider_key = binding.integration_instance.provider_key
    config = binding.integration_instance.get_runtime_config()
    if provider_key == "wecom":
        profile, error_type, error = fetch_member_profile(config, str(external_user.get("userid") or ""))
    elif provider_key == BLUEKING_PROVIDER_KEY:
        profile, error_type, error = retrieve_user_profile(config, str(external_user.get("username") or ""))
    else:
        return external_user
    if error_type or not profile:
        _warn_profile_enrich_failed(binding.id, provider_key, error_type or "invalid_response", error)
        raise _LoginProfileUnavailable()
    return _merge_login_profile(external_user, profile)


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

    external_user = _enrich_external_user_for_create(binding, external_user)

    # 未填默认组织时进入 OpsPilotGuest，以便进入 ops-console 首页后触发
    # init_user_set 首次登录创建组织弹窗。已填写的组织名称仍然优先。
    provider_key = binding.integration_instance.provider_key
    default_group_name = binding.default_group_name
    if not default_group_name and provider_key in _OPS_PILOT_GUEST_PROVIDERS:
        default_group_name = "OpsPilotGuest"

    default_group = None
    if default_group_name:
        default_group, _ = Group.objects.get_or_create(name=default_group_name, parent_id=0)

    if provider_key == "wechat":
        username = external_user.get("openid") or external_value
        display_name = external_user.get("nickname") or username
    else:
        username = external_value
        display_name = external_user.get("name") or username
    email = external_user.get("email", "") if platform_field != "email" else external_value
    phone = external_user.get("mobile", "") if platform_field != "phone" else external_value
    user = User.objects.create(
        user_id=str(uuid.uuid4()),
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
