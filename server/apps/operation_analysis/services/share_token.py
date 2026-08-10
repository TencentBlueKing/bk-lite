import base64
import hmac
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class InvalidShareToken(ValueError):
    pass


PROTOCOL_VERSION = b"\x01"
_PAYLOAD_SIZE = 17
_SIGNATURE_SIZE = 32


def _signing_key():
    value = getattr(settings, "DASHBOARD_SHARE_SIGNING_KEY", "")
    if not value:
        raise ImproperlyConfigured("DASHBOARD_SHARE_SIGNING_KEY must be configured")
    return value.encode("utf-8")


def _decode_base64url(token):
    if not isinstance(token, str) or not token:
        raise InvalidShareToken
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.b64decode(token + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise InvalidShareToken from exc
    canonical_token = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(token, canonical_token):
        raise InvalidShareToken
    return raw


def build_share_token(public_id):
    payload = PROTOCOL_VERSION + public_id.bytes
    signature = hmac.digest(_signing_key(), payload, "sha256")
    return base64.urlsafe_b64encode(payload + signature).rstrip(b"=").decode("ascii")


def parse_share_token(token):
    raw = _decode_base64url(token)
    if len(raw) != _PAYLOAD_SIZE + _SIGNATURE_SIZE:
        raise InvalidShareToken
    payload, supplied_signature = raw[:_PAYLOAD_SIZE], raw[_PAYLOAD_SIZE:]
    if payload[:1] != PROTOCOL_VERSION:
        raise InvalidShareToken
    expected_signature = hmac.digest(_signing_key(), payload, "sha256")
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise InvalidShareToken
    return uuid.UUID(bytes=payload[1:])
