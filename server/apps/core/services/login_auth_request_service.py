from copy import deepcopy
import os
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from django.core import signing
from django.core.cache import cache
from django.utils import timezone

from apps.core.logger import logger

AUTH_REQUEST_PREFIX = "login_auth_request:"
AUTH_REQUEST_TTL = 300
AUTH_REQUEST_SIGNING_SALT = "core.login_auth_request"
LOGIN_RESULT_ALLOWED_KEYS = {
    "id",
    "token",
    "username",
    "display_name",
    "domain",
    "locale",
    "timezone",
    "temporary_pwd",
    "enable_otp",
    "password_expiry_reminder",
    "redirect_url",
    "require_otp",
    "challenge_id",
    "qr_code",
    "need_binding",
}

LOGIN_AUTH_CALLBACK_PATH = "/api/v1/core/api/login_auth/callback/"


def validate_redirect_origin(request, redirect_origin) -> bool:
    """同源校验:浏览器声明的 origin 是否可信任。

    防止 OAuth open-redirector phishing:前端只能声明与请求同源的 origin,
    不同源时调用方需降级到 env/request 兑底。
    优先读 X-Forwarded-Host(反代场景),再回落到 request.get_host()。
    """
    if not redirect_origin or not isinstance(redirect_origin, str):
        return False
    try:
        parsed = urlparse(redirect_origin)
    except (ValueError, TypeError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    if parsed.path not in ("", "/"):
        return False
    if parsed.query or parsed.fragment:
        return False
    forwarded_host = request.META.get("HTTP_X_FORWARDED_HOST")
    if forwarded_host:
        return parsed.netloc == forwarded_host
    return parsed.netloc == request.get_host()


def get_login_auth_callback_uri(request=None, redirect_origin: str | None = None) -> str:
    """生成 login_auth 回调地址。

    优先级:
      1. ``redirect_origin``(同源校验通过时胜出,适用于反代/同源部署可见)
      2. 环境变量 ``DEFAULT_ZONE_VAR_NODE_SERVER_URL``
      3. ``request.build_absolute_uri(...)``(典型 dev / 反代未配置场景)
      4. 空字符串

    该函数同时用于:
      - 集成中心详情页「平台回调地址」展示
      - OAuth 启动流程中飞书/钉钉等 adapter 的 ``redirect_uri``
    """
    base_url = os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "").strip().rstrip("/")
    if (
        redirect_origin
        and request is not None
        and validate_redirect_origin(request, redirect_origin)
    ):
        return f"{redirect_origin.rstrip('/')}{LOGIN_AUTH_CALLBACK_PATH}"
    if base_url:
        return f"{base_url}{LOGIN_AUTH_CALLBACK_PATH}"
    if request is not None:
        return request.build_absolute_uri(LOGIN_AUTH_CALLBACK_PATH)
    return ""


def create_auth_request(binding_id: int, provider_key: str, callback_url: str, redirect_origin: str | None = None) -> dict:
    auth_request_id = str(uuid.uuid4())
    poll_token = str(uuid.uuid4())
    created_at = timezone.now()
    expired_at = created_at + timedelta(seconds=AUTH_REQUEST_TTL)

    auth_request = {
        "auth_request_id": auth_request_id,
        "binding_id": binding_id,
        "provider_key": provider_key,
        "callback_url": callback_url,
        "redirect_origin": redirect_origin or "",
        "poll_token": poll_token,
        "status": "pending",
        "error_message": "",
        "created_at": created_at.isoformat(),
        "expired_at": expired_at.isoformat(),
        "expires_at": expired_at.isoformat(),
        "completed_at": None,
    }
    cache.set(_build_cache_key(auth_request_id), auth_request, timeout=AUTH_REQUEST_TTL)
    logger.info(
        "Created login auth request: auth_request_id=%s, binding_id=%s, provider_key=%s, callback_url=%s, expires_at=%s",
        auth_request_id,
        binding_id,
        provider_key,
        callback_url,
        auth_request["expires_at"],
    )
    return deepcopy(auth_request)


def get_auth_request(auth_request_id: str) -> dict | None:
    if not auth_request_id:
        return None
    auth_request = cache.get(_build_cache_key(auth_request_id))
    if auth_request is None:
        logger.info("Login auth request cache miss: auth_request_id=%s", auth_request_id)
        return None
    return deepcopy(auth_request)


def update_auth_request_status(
    auth_request_id: str,
    status: str,
    error_message: str = "",
    login_result: dict | None = None,
) -> dict | None:
    auth_request = get_auth_request(auth_request_id)
    if not auth_request:
        return None

    auth_request["status"] = status
    auth_request["error_message"] = error_message

    if status == "pending":
        auth_request["completed_at"] = None
    else:
        auth_request["completed_at"] = timezone.now().isoformat()

    if status == "success" and login_result:
        auth_request["login_result"] = _sanitize_login_result(login_result)
    else:
        auth_request.pop("login_result", None)

    cache.set(_build_cache_key(auth_request_id), auth_request, timeout=_get_cache_timeout(auth_request))
    logger.info(
        "Updated login auth request status: auth_request_id=%s, status=%s, error_message=%s",
        auth_request_id,
        status,
        error_message,
    )
    return deepcopy(auth_request)


def build_auth_request_state(auth_request_id: str, binding_id: int, callback_url: str) -> str:
    payload = {
        "auth_request_id": auth_request_id,
        "binding_id": binding_id,
        "callback_url": callback_url,
    }
    return signing.dumps(payload, salt=AUTH_REQUEST_SIGNING_SALT, key=_get_signing_key())


def parse_auth_request_state(state: str) -> dict | None:
    if not state:
        return None
    try:
        payload = signing.loads(state, salt=AUTH_REQUEST_SIGNING_SALT, key=_get_signing_key())
    except signing.BadSignature:
        return None

    auth_request_id = payload.get("auth_request_id")
    binding_id = payload.get("binding_id")
    callback_url = payload.get("callback_url")
    if not auth_request_id or binding_id is None or not callback_url:
        return None

    try:
        binding_id = int(binding_id)
    except (TypeError, ValueError):
        return None

    return {
        "auth_request_id": auth_request_id,
        "binding_id": binding_id,
        "callback_url": callback_url,
    }


def validate_poll_token(auth_request: dict, poll_token: str) -> bool:
    if not auth_request or not poll_token:
        return False
    return auth_request.get("poll_token") == poll_token


def _build_cache_key(auth_request_id: str) -> str:
    return f"{AUTH_REQUEST_PREFIX}{auth_request_id}"


def _get_cache_timeout(auth_request: dict) -> int:
    expired_at = auth_request.get("expired_at")
    if not expired_at:
        return AUTH_REQUEST_TTL

    try:
        expired_at_dt = timezone.datetime.fromisoformat(expired_at)
    except ValueError:
        return AUTH_REQUEST_TTL

    if timezone.is_naive(expired_at_dt):
        expired_at_dt = timezone.make_aware(expired_at_dt, timezone.get_current_timezone())

    remaining_seconds = int((expired_at_dt - timezone.now()).total_seconds())
    return max(remaining_seconds, 1)


def _sanitize_login_result(login_result: dict) -> dict:
    normalized_login_result = deepcopy(login_result)
    if "need_binding" not in normalized_login_result and "need_bindng" in normalized_login_result:
        # Backward-compatible normalization for the historical typo.
        normalized_login_result["need_binding"] = normalized_login_result["need_bindng"]
    return {key: value for key, value in normalized_login_result.items() if key in LOGIN_RESULT_ALLOWED_KEYS}


def _get_signing_key() -> str:
    try:
        return django_settings.SECRET_KEY
    except ImproperlyConfigured:
        return AUTH_REQUEST_SIGNING_SALT
