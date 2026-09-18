"""OpenAPI 密钥 Scope：全部，或内部接口 / 外部服务前缀名单。"""

from apps.core.openapi.registry import METHODS, SERVICE_NAME_RE

MODE_ALL = "all"
MODE_ALLOWLIST = "allowlist"
SCOPE_ALL = {"mode": MODE_ALL}

_EXTERNAL_PREFIX = "EXTERNAL "


def endpoint_key(method: str, path: str) -> str:
    return f"{method} {path}"


def external_key(service: str) -> str:
    return f"{_EXTERNAL_PREFIX}{service}"


def _is_internal_key(value) -> bool:
    if not isinstance(value, str):
        return False
    method, _, path = value.partition(" ")
    if method not in METHODS or not path or "/" not in path:
        return False
    service, _, sub_path = path.partition("/")
    return bool(sub_path) and SERVICE_NAME_RE.fullmatch(service) is not None


def _is_external_key(value) -> bool:
    if not isinstance(value, str) or not value.startswith(_EXTERNAL_PREFIX):
        return False
    service = value[len(_EXTERNAL_PREFIX):]
    return SERVICE_NAME_RE.fullmatch(service) is not None


def is_endpoint_key(value) -> bool:
    return _is_internal_key(value) or _is_external_key(value)


def is_canonical_scope(scope) -> bool:
    if not isinstance(scope, dict):
        return False
    mode = scope.get("mode")
    extra = set(scope) - {"mode", "endpoints"}
    if extra:
        return False
    if mode == MODE_ALL:
        return "endpoints" not in scope
    if mode != MODE_ALLOWLIST:
        return False
    endpoints = scope.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        return False
    seen = set()
    for item in endpoints:
        if not is_endpoint_key(item) or item in seen:
            return False
        seen.add(item)
    return True


def normalize_scope(scope):
    """校验并返回规范化 Scope。非法时抛 ValueError。"""
    if not is_canonical_scope(scope):
        raise ValueError("scope must be {mode: all} or {mode: allowlist, endpoints: [...]}")
    if scope["mode"] == MODE_ALL:
        return {"mode": MODE_ALL}
    return {
        "mode": MODE_ALLOWLIST,
        "endpoints": list(scope["endpoints"]),
    }


def migrate_stored_scope(scope):
    if is_canonical_scope(scope):
        return normalize_scope(scope)
    return dict(SCOPE_ALL)


def allows_internal(scope, method: str, path: str) -> bool:
    effective = migrate_stored_scope(scope)
    if effective["mode"] == MODE_ALL:
        return True
    return endpoint_key(method, path) in effective["endpoints"]


def allows_external(scope, service: str) -> bool:
    effective = migrate_stored_scope(scope)
    if effective["mode"] == MODE_ALL:
        return True
    return external_key(service) in effective["endpoints"]
