from copy import deepcopy
import uuid
from datetime import timedelta

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
    "need_bindng",
}


def create_auth_request(binding_id: int, provider_key: str, callback_url: str) -> dict:
    auth_request_id = str(uuid.uuid4())
    poll_token = str(uuid.uuid4())
    created_at = timezone.now()
    expired_at = created_at + timedelta(seconds=AUTH_REQUEST_TTL)

    auth_request = {
        "auth_request_id": auth_request_id,
        "binding_id": binding_id,
        "provider_key": provider_key,
        "callback_url": callback_url,
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
    return {key: value for key, value in login_result.items() if key in LOGIN_RESULT_ALLOWED_KEYS}


def _get_signing_key() -> str:
    try:
        return django_settings.SECRET_KEY
    except ImproperlyConfigured:
        return AUTH_REQUEST_SIGNING_SALT
