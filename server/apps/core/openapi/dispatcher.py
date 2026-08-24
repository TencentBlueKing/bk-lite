"""invoke 分发器：权限位 → schema 校验 → 身份注入 → 本地调用 → envelope 包装。

身份注入不变式（design.md 3.3.1，安全红线 2）：
- 身份（user / 授权组织集合）只来自认证结果；
- 选择（组织锚点等业务参数）可来自客户端，但被校验或被函数内权限逻辑自然约束；
- 客户端请求中的身份字段在 schema 层已无法混入（serializer 拒绝未知字段，
  registry 拒绝声明身份字段）。

强制超时：settings.OPENAPI_INVOKE_TIMEOUT > 0 时经线程池施加硬超时
（生产配置）；为 0 时同步执行（开发 / 测试，pytest 事务型用例依赖同连接）。
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

from django.conf import settings

from apps.core.logger import openapi_logger as logger
from apps.core.openapi.envelope import ErrorCode, fail, ok
from apps.core.openapi.identity import CREDENTIAL_API_TOKEN, CallerIdentity
from apps.core.openapi.registry import INJECT_TEAM_LIST, INJECT_TEAM_LIST_WITH_USER, INJECT_USER_INFO, Endpoint

_executor = None

# 现有 nats_api 以自由文本 message 表达组织越权（无结构化 code），网关据此
# 映射到冻结清单定义的 TEAM_OUT_OF_SCOPE(403)。暴露函数改用结构化错误码后，
# 本表可随之退役（见 m1-notes 软错误映射）。
_TEAM_SCOPE_MARKERS = ("无权访问该组织", "无权限访问该组织", "组织数据", "out of scope")


def _get_executor():
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=int(getattr(settings, "OPENAPI_INVOKE_POOL_SIZE", 8)),
            thread_name_prefix="openapi-invoke",
        )
    return _executor


def _check_permission(identity: CallerIdentity, endpoint: Endpoint) -> bool:
    """复用 HasPermission 同款权限数据模型（app → 权限名集合）自行实现等价判断。

    fail-closed：声明了 permission 而用户权限数据为空时拒绝。
    """
    if not endpoint.permission:
        return True
    if identity.is_superuser:
        return True
    required = {p.strip() for p in endpoint.permission.split(",") if p.strip()}
    granted = identity.permission.get(endpoint.permission_app, set())
    if not isinstance(granted, set):
        granted = set(granted or [])
    return bool(required & granted)


def _build_kwargs(identity: CallerIdentity, endpoint: Endpoint, validated: dict):
    kwargs = dict(validated)
    for schema_field, param_name in endpoint.param_map.items():
        if schema_field in kwargs:
            kwargs[param_name] = kwargs.pop(schema_field)

    if endpoint.team_free:
        return kwargs

    if endpoint.inject == INJECT_TEAM_LIST:
        kwargs["team"] = list(identity.team_ids)
        return kwargs

    if endpoint.inject == INJECT_TEAM_LIST_WITH_USER:
        kwargs["team"] = list(identity.team_ids)
        kwargs["user_info"] = {"user": identity.user, "domain": identity.domain}
        return kwargs

    if endpoint.inject == INJECT_USER_INFO:
        user_info = {"user": identity.user, "domain": identity.domain}
        anchor = kwargs.pop("team", None)
        include_children = kwargs.pop("include_children", None)
        if identity.credential_type == CREDENTIAL_API_TOKEN:
            # API 令牌为单组织收窄凭据：锚点强制取绑定组织，客户端传值被覆盖
            anchor = identity.team_ids[0] if identity.team_ids else None
        if anchor is None:
            return kwargs, fail(
                ErrorCode.SCHEMA_INVALID, "team (organization anchor) is required"
            )
        user_info["team"] = int(anchor)
        if include_children is not None:
            user_info["include_children"] = bool(include_children)
        kwargs["user_info"] = user_info
        return kwargs

    return kwargs


def _call(endpoint: Endpoint, kwargs: dict):
    timeout = float(getattr(settings, "OPENAPI_INVOKE_TIMEOUT", 0) or 0)
    if timeout <= 0:
        return endpoint.func(**kwargs)
    future = _get_executor().submit(endpoint.func, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FutureTimeoutError:
        future.cancel()
        raise


def dispatch(identity: CallerIdentity, endpoint: Endpoint, payload: dict):
    if not _check_permission(identity, endpoint):
        return fail(ErrorCode.PERM_MISSING, "permission denied")

    serializer = endpoint.serializer_class(data=payload)
    if not serializer.is_valid():
        detail = "; ".join(
            f"{name}: {errors[0]}" for name, errors in list(serializer.errors.items())[:5]
        )
        return fail(ErrorCode.SCHEMA_INVALID, detail or "invalid request")

    built = _build_kwargs(identity, endpoint, dict(serializer.validated_data))
    if isinstance(built, tuple):
        return built[1]

    try:
        result = _call(endpoint, built)
    except FutureTimeoutError:
        logger.warning("openapi invoke timeout: %s", endpoint.path)
        return fail(ErrorCode.TIMEOUT, "invoke timeout")
    except Exception:
        logger.exception("openapi invoke error: %s", endpoint.path)
        return fail(ErrorCode.INTERNAL_ERROR, "internal error")

    # 现有 nats_api 软错误约定 {"result": False, "message": ...} 统一映射。
    # 组织越权类软错误单独识别为 TEAM_OUT_OF_SCOPE(403)：函数按注入的授权集合
    # 拒绝越界组织参数是网关的核心授权语义，冻结清单为其定义了专属错误码，
    # 不能与普通业务拒绝混为 400。
    if isinstance(result, dict) and result.get("result") is False:
        message = str(result.get("message", "rejected"))
        if any(marker in message for marker in _TEAM_SCOPE_MARKERS):
            return fail(ErrorCode.TEAM_OUT_OF_SCOPE, message)
        return fail(ErrorCode.BUSINESS_REJECTED, message)
    return ok(result)
