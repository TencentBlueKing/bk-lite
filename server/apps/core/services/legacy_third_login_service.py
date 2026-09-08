import secrets
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings as django_settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from apps.core.logger import logger

CODE_TTL_SECONDS = 300
CACHE_KEY_PREFIX = "legacy_third_login_code:"
ISSUE_RETRY_LIMIT = 5
GENERIC_EXCHANGE_ERROR = "Invalid or expired code"


def get_allowed_callback_hosts() -> set[str]:
    raw = getattr(django_settings, "LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS", "") or ""
    if isinstance(raw, (list, tuple, set, frozenset)):
        parts = raw
    else:
        parts = str(raw).split(",")
    return {str(part).strip().lower() for part in parts if str(part).strip()}


def callback_hostname(callback_url: str) -> str | None:
    try:
        parsed = urlparse(callback_url)
    except (TypeError, ValueError):
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    return hostname.lower()


def is_safe_legacy_external_callback_url(callback_url: str) -> bool:
    if not isinstance(callback_url, str) or not callback_url:
        return False
    try:
        parsed = urlparse(callback_url)
    except (TypeError, ValueError):
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False
    return hostname.lower() in get_allowed_callback_hosts()


def origin_hostname(origin: str | None) -> str | None:
    if not origin:
        return None
    try:
        parsed = urlparse(origin)
    except (TypeError, ValueError):
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    hostname = parsed.hostname
    if not hostname:
        return None
    return hostname.lower()


def _cache_key(code: str) -> str:
    return f"{CACHE_KEY_PREFIX}{code}"


def issue_legacy_third_login_code(*, token: str, callback_url: str) -> str | None:
    hostname = callback_hostname(callback_url)
    if not token or not hostname or not is_safe_legacy_external_callback_url(callback_url):
        logger.info("event=legacy_third_login_code_issued result=rejected callback_host=%s", hostname or "-")
        return None

    payload = {
        "token": token,
        "callback_host": hostname,
        "issued_at": timezone.now().isoformat(),
    }
    for _ in range(ISSUE_RETRY_LIMIT):
        code = secrets.token_urlsafe(32)
        if cache.add(_cache_key(code), payload, CODE_TTL_SECONDS):
            logger.info("event=legacy_third_login_code_issued result=success callback_host=%s", hostname)
            return code

    logger.error(
        "event=legacy_third_login_code_issue_failed failed_stage=cache_add error_type=Collision callback_host=%s",
        hostname,
    )
    return None


def build_legacy_redirect_url(callback_url: str, third_login_code: str, bk_lite_code: str) -> str | None:
    if not third_login_code or not bk_lite_code or not is_safe_legacy_external_callback_url(callback_url):
        return None
    try:
        parsed = urlparse(callback_url)
    except (TypeError, ValueError):
        return None
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in ("token", "bk_lite_code", "third_login_code")
    ]
    query_items.append(("third_login_code", third_login_code))
    query_items.append(("bk_lite_code", bk_lite_code))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def authorize_legacy_redirect(*, token: str, callback_url: str, third_login_code: str) -> str | None:
    hostname = callback_hostname(callback_url)
    if not third_login_code or not is_safe_legacy_external_callback_url(callback_url):
        logger.info("event=legacy_third_login_authorized result=rejected callback_host=%s", hostname or "-")
        return None
    code = issue_legacy_third_login_code(token=token, callback_url=callback_url)
    if not code:
        logger.info("event=legacy_third_login_authorized result=rejected callback_host=%s", hostname or "-")
        return None
    redirect_url = build_legacy_redirect_url(callback_url, third_login_code, code)
    if not redirect_url:
        logger.info("event=legacy_third_login_authorized result=rejected callback_host=%s", hostname or "-")
        return None
    logger.info("event=legacy_third_login_authorized result=success callback_host=%s", hostname)
    return redirect_url


def consume_legacy_third_login_code(code: str, request_origin: str | None) -> dict | None:
    if not code:
        logger.info("event=legacy_third_login_exchanged result=rejected reason=invalid")
        return None
    key = _cache_key(code)
    payload = cache.get(key)
    if not isinstance(payload, dict):
        logger.info("event=legacy_third_login_exchanged result=rejected reason=invalid")
        return None
    request_host = origin_hostname(request_origin)
    callback_host = payload.get("callback_host")
    if not request_host or request_host != callback_host:
        logger.info("event=legacy_third_login_exchanged result=rejected callback_host=%s", callback_host or "-")
        return None
    if not cache.delete(key):
        logger.info("event=legacy_third_login_exchanged result=rejected callback_host=%s", callback_host)
        return None
    if not payload.get("token"):
        logger.info("event=legacy_third_login_exchanged result=rejected callback_host=%s", callback_host)
        return None
    logger.info("event=legacy_third_login_exchanged result=success callback_host=%s", callback_host)
    return payload


def cors_origin_for_request(request) -> str | None:
    origin = request.META.get("HTTP_ORIGIN", "")
    hostname = origin_hostname(origin)
    if not hostname or hostname not in get_allowed_callback_hosts():
        return None
    try:
        parsed = urlparse(origin)
    except (TypeError, ValueError):
        return None
    if parsed.scheme not in ("http", "https"):
        return None
    return origin


def apply_exchange_cors(request, response):
    origin = cors_origin_for_request(request)
    if not origin:
        return response
    response["Access-Control-Allow-Origin"] = origin
    response["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type"
    response["Access-Control-Max-Age"] = "600"
    response["Vary"] = "Origin"
    return response


def extract_bearer_token(request) -> str:
    header = request.META.get(getattr(django_settings, "AUTH_TOKEN_HEADER_NAME", "HTTP_AUTHORIZATION"), "")
    if not header:
        header = request.META.get("HTTP_AUTHORIZATION", "")
    token = str(header).strip()
    if token.startswith("Bearer "):
        return token[7:].strip()
    return token


def json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"result": False, "message": message}, status=status)
