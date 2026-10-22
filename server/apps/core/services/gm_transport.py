"""国密传输运行时：解开请求、防重放、封响应。

信封格式在 ``apps.core.utils.crypto.gm_transport``。这里只处理请求生命周期。
"""

import base64
import binascii
import hmac
import json
import math
import os
import secrets
import tempfile
import time
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse

from apps.core.logger import logger, safe_exception_info, safe_log_value
from apps.core.utils.crypto.gm_transport import (
    GmTransportCryptoError,
    decrypt_sm4_cbc,
    encrypt_sm4_cbc,
    hmac_sm3,
    kid_from_public_key_hex,
    public_key_hex_from_private,
    request_mac_message,
    seal_response_envelope,
    unframe_plaintext,
    unwrap_sm4_key,
    wrap_sm4_key,
)
from apps.core.utils.loader import LanguageLoader

WINDOW_MS = 300_000
MAX_ENVELOPE_BYTES = 280 * 1024 * 1024
MAX_RESPONSE_BYTES = 200 * 1024 * 1024
API_PREFIX = "/api/v1"
PUBLIC_PATH = "/api/v1/core/api/gm_transport_public"
NONCE_KEY = "gm_transport:nonce:{nonce}"
SETTING_KEY = "enable_gm_transport"
SM2_ORDER = int("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFF7203DF6B21C6052B53BBF40939D54123", 16)
_REQUIRED = ("v", "ts", "nonce", "kid", "method", "path", "cty", "ek", "iv", "ct", "mac")
_STATUS = {
    "gm_transport_rejected": 400,
    "gm_transport_expired": 400,
    "gm_transport_replay": 400,
    "gm_transport_unavailable": 503,
    "gm_transport_too_large": 413,
}

_degraded_stage = None


@dataclass
class TransportFailure:
    code: str
    kid: str = ""
    stage: str = ""
    exc: BaseException | None = None

    @property
    def status(self) -> int:
        return _STATUS[self.code]


@dataclass
class OpenedTransport:
    method: str
    query: str
    body: bytes
    cty: str
    sm4_key: bytes
    nonce: str


def server_now_ms() -> int:
    return time.time_ns() // 1_000_000


def cache_is_redis() -> bool:
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return backend.endswith("RedisCache")


def load_private_key() -> str:
    return os.environ.get("GM_SM2_PRIVATE_KEY", "").strip()


def private_key_problem() -> str | None:
    key = load_private_key()
    if not key:
        return "gm_transport_private_key_missing"
    if len(key) != 64:
        return "gm_transport_private_key_invalid"
    try:
        value = int(key, 16)
    except ValueError:
        return "gm_transport_private_key_invalid"
    if not 1 <= value <= SM2_ORDER - 2:
        return "gm_transport_private_key_invalid"
    try:
        public_key_hex_from_private(key)
    except GmTransportCryptoError:
        return "gm_transport_private_key_invalid"
    return None


def transport_enabled() -> str:
    from apps.system_mgmt.models import SystemSettings

    row = SystemSettings.objects.filter(key=SETTING_KEY).only("value").first()
    if row is None or str(row.value) != "1":
        return "0"
    return "1"


def note_degraded(stage: str, exc: BaseException | None = None) -> None:
    global _degraded_stage
    if _degraded_stage == stage:
        logger.debug("event=gm_transport_degraded failed_stage=%s error_type=gm_transport_unavailable", stage)
        return
    logger.error(
        "event=gm_transport_degraded failed_stage=%s error_type=gm_transport_unavailable",
        stage,
        exc_info=None if exc is None else safe_exception_info(exc),
    )
    _degraded_stage = stage


def note_ready() -> None:
    global _degraded_stage
    if _degraded_stage is None:
        return
    logger.info("event=gm_transport_ready")
    _degraded_stage = None


def reset_degrade_state() -> None:
    global _degraded_stage
    _degraded_stage = None


def public_payload() -> dict:
    if transport_enabled() != "1":
        note_ready()
        return {"enabled": "0"}
    problem = private_key_problem()
    if problem:
        note_degraded("private_key")
        return {"enabled": "0", "degraded": "1"}
    if not cache_is_redis():
        note_degraded("cache")
        return {"enabled": "0", "degraded": "1"}
    public_key = public_key_hex_from_private(load_private_key())
    note_ready()
    return {"enabled": "1", "kid": kid_from_public_key_hex(public_key), "public_key": public_key}


def self_check_failure() -> str | None:
    problem = private_key_problem()
    if problem:
        return problem
    if not cache_is_redis():
        return "gm_transport_cache_unavailable"
    probe = "gm_transport:selfcheck:" + secrets.token_hex(8)
    try:
        added = cache.add(probe, "1", timeout=30)
        if not added:
            return "gm_transport_cache_unavailable"
        cache.delete(probe)
    except Exception as exc:
        _log_self_check_failure("cache", exc)
        return "gm_transport_cache_unavailable"
    try:
        _algorithm_roundtrip(load_private_key())
    except Exception as exc:
        _log_self_check_failure("algorithm", exc)
        return "gm_transport_self_check_failed"
    return None


def _log_self_check_failure(stage: str, exc: BaseException) -> None:
    logger.error(
        "event=gm_transport_self_check_failed failed_stage=%s error_type=%s",
        stage,
        type(exc).__name__,
        exc_info=safe_exception_info(exc),
    )


def _algorithm_roundtrip(private_key: str) -> None:
    public_key = public_key_hex_from_private(private_key)
    sm4_key = os.urandom(16)
    wrapped = wrap_sm4_key(public_key, sm4_key)
    opened = unwrap_sm4_key(private_key, wrapped)
    if opened != sm4_key:
        raise GmTransportCryptoError("sm4 key mismatch")
    body = b"gm-transport-self-check"
    iv = os.urandom(16)
    ciphertext = encrypt_sm4_cbc(sm4_key, iv, body)
    if decrypt_sm4_cbc(sm4_key, iv, ciphertext) != body:
        raise GmTransportCryptoError("sm4 mismatch")
    message = b"gm-transport-self-check"
    mac = hmac_sm3(sm4_key, message)
    if (
        len(mac) != 32
        or not hmac.compare_digest(mac, hmac_sm3(sm4_key, message))
        or hmac.compare_digest(mac, hmac_sm3(sm4_key, message + b"x"))
        or hmac.compare_digest(mac, hmac_sm3(os.urandom(16), message))
    ):
        raise GmTransportCryptoError("hmac mismatch")


def request_locale(request) -> str:
    raw = request.META.get("HTTP_X_BK_LOCALE") or ""
    if not raw:
        raw = (request.META.get("HTTP_ACCEPT_LANGUAGE") or "").split(",")[0]
    return raw or "zh-Hans"


def translated(request, code: str) -> str:
    message = LanguageLoader(app="core", default_lang=request_locale(request)).get(f"error.{code}", code)
    return message if isinstance(message, str) else code


def error_response(request, code: str, status: int | None = None) -> JsonResponse:
    return JsonResponse(
        {"result": False, "message": translated(request, code), "code": code},
        status=status if status is not None else _STATUS.get(code, 400),
    )


def log_client_failure(request, failure: TransportFailure) -> None:
    logger.warning(
        "event=gm_transport_rejected path=%s kid=%s error_type=%s",
        safe_log_value(request.path),
        safe_log_value(failure.kid),
        failure.code,
    )
    if failure.code == "gm_transport_unavailable" and failure.stage:
        note_degraded(failure.stage, failure.exc)


def log_unexpected(request, exc: BaseException, stage: str) -> None:
    logger.error(
        "event=gm_transport_failed path=%s failed_stage=%s error_type=%s",
        safe_log_value(request.path),
        stage,
        type(exc).__name__,
        exc_info=safe_exception_info(exc),
    )


def api_relative_path(path: str) -> str:
    if path.startswith(API_PREFIX):
        return path[len(API_PREFIX) :] or "/"
    return path


def is_public_path(path: str) -> bool:
    return path.rstrip("/") == PUBLIC_PATH


def open_request(request) -> OpenedTransport | TransportFailure:
    raw, read_failure = _read_envelope(request)
    if read_failure:
        return TransportFailure(read_failure)
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return TransportFailure("gm_transport_rejected")
    del raw
    kid = envelope.get("kid") if isinstance(envelope, dict) and isinstance(envelope.get("kid"), str) else ""
    if not isinstance(envelope, dict) or any(name not in envelope for name in _REQUIRED):
        return TransportFailure("gm_transport_rejected", kid=kid)
    if envelope.get("v") != 1 or isinstance(envelope.get("v"), bool):
        return TransportFailure("gm_transport_rejected", kid=kid)
    if not _fields_are_text(envelope):
        return TransportFailure("gm_transport_rejected", kid=kid)
    if not _method_accepted(request, envelope["method"]) or envelope["path"] != api_relative_path(request.path):
        return TransportFailure("gm_transport_rejected", kid=kid)
    now_ms = server_now_ms()
    if abs(now_ms - envelope["ts"]) > WINDOW_MS:
        return TransportFailure("gm_transport_expired", kid=kid)
    problem = private_key_problem()
    if problem:
        return TransportFailure("gm_transport_unavailable", kid=kid, stage="private_key")
    private_key = load_private_key()
    public_key = public_key_hex_from_private(private_key)
    if envelope["kid"] != kid_from_public_key_hex(public_key):
        return TransportFailure("gm_transport_rejected", kid=kid)
    try:
        sm4_key = unwrap_sm4_key(private_key, _b64decode(envelope["ek"]))
        message = request_mac_message(
            ts=envelope["ts"],
            nonce=envelope["nonce"],
            method=envelope["method"],
            path=envelope["path"],
            cty=envelope["cty"],
            iv_b64=envelope["iv"],
            ct_b64=envelope["ct"],
        )
        expected = hmac_sm3(sm4_key, message)
        mac = _b64decode(envelope["mac"])
    except GmTransportCryptoError:
        return TransportFailure("gm_transport_rejected", kid=kid)
    if len(expected) != len(mac) or not hmac.compare_digest(expected, mac):
        return TransportFailure("gm_transport_rejected", kid=kid)
    if not cache_is_redis():
        return TransportFailure("gm_transport_unavailable", kid=kid, stage="cache")
    ttl = max(1, math.ceil((envelope["ts"] + WINDOW_MS - now_ms) / 1000))
    try:
        added = cache.add(NONCE_KEY.format(nonce=envelope["nonce"]), "1", timeout=ttl)
    except Exception as exc:
        return TransportFailure("gm_transport_unavailable", kid=kid, stage="cache", exc=exc)
    if not added:
        return TransportFailure("gm_transport_replay", kid=kid)
    try:
        plaintext = decrypt_sm4_cbc(sm4_key, _b64decode(envelope["iv"]), _b64decode(envelope["ct"]))
        query, body = unframe_plaintext(plaintext)
    except GmTransportCryptoError:
        return TransportFailure("gm_transport_rejected", kid=kid)
    return OpenedTransport(
        method=envelope["method"],
        query=query,
        body=body,
        cty=envelope["cty"],
        sm4_key=sm4_key,
        nonce=envelope["nonce"],
    )


def install_plaintext(request, opened: OpenedTransport) -> None:
    spool = tempfile.SpooledTemporaryFile(max_size=settings.FILE_UPLOAD_MAX_MEMORY_SIZE, mode="w+b")
    spool.write(opened.body)
    spool.seek(0)
    request._stream = spool
    request._read_started = False
    if hasattr(request, "_body"):
        del request._body
    request.META["CONTENT_LENGTH"] = str(len(opened.body))
    request.META["CONTENT_TYPE"] = opened.cty
    request._set_content_type_params(request.META)
    request.META["QUERY_STRING"] = opened.query.encode("utf-8").decode("iso-8859-1")
    if hasattr(request, "_get"):
        del request._get
    request.method = opened.method
    request.META["REQUEST_METHOD"] = opened.method
    request.META.pop("HTTP_X_GM_TRANSPORT", None)
    request._gm_transport = opened


def _response_is_json(response) -> bool:
    return "json" in response.get("Content-Type", "").lower()


def seal_response(request, response):
    opened = getattr(request, "_gm_transport", None)
    if opened is None:
        return response
    if response.status_code in (204, 304):
        return response
    if getattr(response, "streaming", False):
        return response
    if not _response_is_json(response):
        return response
    body = response.content
    if not body:
        return response
    if len(body) > MAX_RESPONSE_BYTES:
        return error_response(request, "gm_transport_too_large")
    sealed = _seal_bytes(opened, response.status_code, response.get("Content-Type", ""), body, seq=1)
    outgoing = HttpResponse(sealed, status=response.status_code, content_type="application/json")
    for header, value in response.items():
        if header.lower() in {"content-type", "content-length"}:
            continue
        outgoing[header] = value
    outgoing.cookies.update(response.cookies)
    outgoing["X-Gm-Transport"] = "1"
    return outgoing


def _read_envelope(request) -> tuple[bytes | None, str | None]:
    declared = request.META.get("CONTENT_LENGTH")
    try:
        size = int(declared) if declared not in (None, "") else None
    except (TypeError, ValueError):
        return None, "gm_transport_rejected"
    if size is not None and size > MAX_ENVELOPE_BYTES:
        return None, "gm_transport_too_large"
    stream = request._stream
    if size is None:
        chunks = []
        remaining = MAX_ENVELOPE_BYTES + 1
        while remaining > 0:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > MAX_ENVELOPE_BYTES:
            return None, "gm_transport_too_large"
        return data, None
    return stream.read(size) or b"", None


def _fields_are_text(envelope: dict) -> bool:
    ts = envelope["ts"]
    if isinstance(ts, bool) or not isinstance(ts, int):
        return False
    return all(isinstance(envelope[name], str) for name in ("nonce", "kid", "method", "path", "cty", "ek", "iv", "ct", "mac"))


def _method_accepted(request, envelope_method: str) -> bool:
    wire = request.method.upper()
    if envelope_method == "GET":
        return wire == "POST"
    return envelope_method == wire


def _seal_bytes(opened: OpenedTransport, status: int, cty: str, body: bytes, seq: int) -> bytes:
    envelope = seal_response_envelope(
        sm4_key=opened.sm4_key,
        iv=os.urandom(16),
        nonce=opened.nonce,
        seq=seq,
        status=status,
        cty=cty or "",
        body=body,
    )
    return json.dumps(envelope, separators=(",", ":")).encode("utf-8")


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise GmTransportCryptoError("envelope field is not base64") from exc


def unexpected_response(request) -> JsonResponse:
    return JsonResponse(
        {"result": False, "message": translated(request, "system_error"), "code": "system_error"},
        status=500,
    )
