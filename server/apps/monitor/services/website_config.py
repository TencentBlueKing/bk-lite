"""Validation and normalization for the Website Telegraf input."""

import re
from urllib.parse import urlencode, urlsplit, urlunsplit


SUPPORTED_METHODS = {"GET", "HEAD", "POST"}
MIN_HTTP_STATUS_CODE = 100
MAX_HTTP_STATUS_CODE = 599
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 600


def normalize_website_request_config(config: dict) -> dict:
    """Return a validated Website config with its final request URL.

    The same rule is deliberately applied before a persistent config is
    rendered and before a one-off Telegraf check is executed.  Clients must
    not be able to bypass it by posting directly to either API.
    """
    normalized = {**config}
    url = str(normalized.get("url") or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("URL 必须是有效的 HTTP 或 HTTPS 地址")
    if parts.query:
        raise ValueError("URL 不允许包含 query 参数，请在请求参数中填写")
    if parts.fragment:
        raise ValueError("URL 不允许包含 fragment")

    params = _normalize_entries(normalized.get("request_params"), "请求参数")
    headers = _normalize_headers(normalized.get("request_headers"))
    query = urlencode([(item["key"], item["value"]) for item in params], doseq=True)
    normalized["request_params"] = params
    normalized["request_headers"] = headers
    normalized["request_url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))

    method = str(normalized.get("request_method") or "GET").upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError("请求方式仅支持 GET、HEAD 或 POST")
    if method != "POST" and normalized.get("request_body") not in (None, ""):
        raise ValueError("仅 POST 请求允许填写请求体")
    normalized["request_method"] = method

    _validate_optional_int(normalized.get("response_status_code"), "期望状态码", MIN_HTTP_STATUS_CODE, MAX_HTTP_STATUS_CODE)
    _validate_optional_int(normalized.get("response_timeout"), "请求超时", MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS)

    auth_type = str(normalized.get("auth_type") or "none")
    if auth_type not in {"none", "basic", "bearer"}:
        raise ValueError("认证方式仅支持无认证、Basic Auth 或 Bearer Token")
    if auth_type == "basic":
        _require_value(normalized.get("username"), "Basic Auth 用户名")
        _require_value(normalized.get("ENV_PASSWORD"), "Basic Auth 密码")
    if auth_type == "bearer":
        _require_value(normalized.get("ENV_BEARER_TOKEN"), "Bearer Token")
    normalized["auth_type"] = auth_type
    # 前端可选开关缺省时可能被补成 ""；空串会让 Jinja default(false) 渲出非法 TOML。
    normalized["insecure_skip_verify"] = _coerce_bool(normalized.get("insecure_skip_verify"), False)
    return normalized


def validate_rendered_website_config(config: dict, env_config: dict | None = None) -> None:
    """Validate the TOML-shaped config used by the edit API."""
    env_config = env_config or {}
    # 编辑接口 content 通常是 ConfigFormat 形态 {plugin, config}；兼容扁平 config。
    target = (
        config["config"]
        if isinstance(config.get("config"), dict) and config.get("plugin") is not None
        else config
    )
    urls = target.get("urls") or []
    if not isinstance(urls, list) or len(urls) != 1:
        raise ValueError("网站拨测必须配置一个 URL")
    parts = urlsplit(str(urls[0] or ""))
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.fragment:
        raise ValueError("URL 必须是有效的 HTTP 或 HTTPS 地址，且不能包含 fragment")

    method = str(target.get("method") or "GET").upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError("请求方式仅支持 GET、HEAD 或 POST")
    if method != "POST" and target.get("body") not in (None, ""):
        raise ValueError("仅 POST 请求允许填写请求体")
    _validate_optional_int(target.get("response_status_code"), "期望状态码", MIN_HTTP_STATUS_CODE, MAX_HTTP_STATUS_CODE)
    timeout = target.get("response_timeout")
    if isinstance(timeout, str) and timeout.endswith("s"):
        timeout = timeout[:-1]
    _validate_optional_int(timeout, "请求超时", MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS)
    # 空串/缺省统一成 bool，避免 toml.dumps 写出 insecure_skip_verify = ""。
    target["insecure_skip_verify"] = _coerce_bool(target.get("insecure_skip_verify"), False)
    headers = target.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("请求头必须是键值列表")
    authorization_values = [value for key, value in headers.items() if str(key).lower() == "authorization"]
    if len(authorization_values) > 1:
        raise ValueError("请求头名称重复：Authorization")
    authorization = authorization_values[0] if authorization_values else None
    non_authorization_headers = [
        {"key": key, "value": value}
        for key, value in headers.items()
        if str(key).lower() != "authorization"
    ]
    _normalize_headers(non_authorization_headers)
    username = target.get("username")
    password = target.get("password")
    if username or password:
        _require_value(username, "Basic Auth 用户名")
        password_env_key = _extract_env_reference(password, "PASSWORD")
        if not password_env_key or env_config.get(password_env_key) in (None, ""):
            raise ValueError("Basic Auth 密码不能为空")
    if authorization is not None:
        bearer_env_key = _extract_bearer_env_reference(authorization)
        if not bearer_env_key:
            raise ValueError("Authorization 请求头请使用认证配置")
        if env_config.get(bearer_env_key) in (None, ""):
            raise ValueError("Bearer Token 不能为空")


def _coerce_bool(value, default=False):
    """Normalize optional TLS/switch values before Telegraf TOML render/edit."""
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        raise ValueError("跳过证书校验必须是布尔值")
    raise ValueError("跳过证书校验必须是布尔值")


def _normalize_entries(entries, field_name):
    if entries in (None, ""):
        return []
    if not isinstance(entries, list):
        raise ValueError(f"{field_name}必须是键值列表")
    normalized = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{field_name}格式不正确")
        key = str(entry.get("key") or "").strip()
        value = str(entry.get("value") or "")
        if not key and not value.strip():
            continue
        if not key:
            raise ValueError(f"{field_name}名称不能为空")
        normalized.append({"key": key, "value": value})
    return normalized


def _normalize_headers(entries):
    if isinstance(entries, dict):
        entries = [{"key": key, "value": value} for key, value in entries.items()]
    headers = _normalize_entries(entries, "请求头")
    names = set()
    for header in headers:
        normalized_name = header["key"].lower()
        if normalized_name == "authorization":
            raise ValueError("Authorization 请求头请使用认证配置")
        if normalized_name in names:
            raise ValueError(f"请求头名称重复：{header['key']}")
        names.add(normalized_name)
    return headers


def _validate_optional_int(value, field_name, minimum, maximum):
    if value in (None, ""):
        return
    if isinstance(value, bool):
        raise ValueError(f"{field_name}必须在 {minimum} 到 {maximum} 之间")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须在 {minimum} 到 {maximum} 之间")
    if str(number) != str(value).strip() or not minimum <= number <= maximum:
        raise ValueError(f"{field_name}必须在 {minimum} 到 {maximum} 之间")


def _require_value(value, field_name):
    if value in (None, ""):
        raise ValueError(f"{field_name}不能为空")


def _extract_env_reference(value, prefix):
    match = re.fullmatch(rf"\$\{{({prefix}__[A-Za-z0-9_]+)\}}", str(value or ""))
    return match.group(1) if match else ""


def _extract_bearer_env_reference(value):
    match = re.fullmatch(r"Bearer \$\{(BEARER_TOKEN__[A-Za-z0-9_]+)\}", str(value or ""))
    return match.group(1) if match else ""
