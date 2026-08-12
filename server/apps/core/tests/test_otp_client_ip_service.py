"""OTP client-IP attribution service and HTTP-boundary contract tests."""

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache, caches
from django.test import RequestFactory

from apps.core.views import index_view


@pytest.fixture
def locmem_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "otp-client-ip-contract",
        }
    }
    caches["default"].clear()
    yield cache
    caches["default"].clear()


def _otp_request(*, remote_addr="", forwarded_for=""):
    request = RequestFactory().post(
        "/api/v1/core/api/verify_otp_login/",
        data=json.dumps({"challenge_id": "ch", "otp_code": "999999"}),
        content_type="application/json",
        REMOTE_ADDR=remote_addr,
    )
    if forwarded_for:
        request.META["HTTP_X_FORWARDED_FOR"] = forwarded_for
    return request


def test_direct_mode_ignores_untrusted_x_forwarded_for(monkeypatch):
    monkeypatch.delenv("OTP_CLIENT_IP_MODE", raising=False)
    request = _otp_request(remote_addr="9.9.9.9", forwarded_for="1.1.1.1, 2.2.2.2")

    assert index_view._get_client_ip(request) == "9.9.9.9"


def test_direct_mode_uses_empty_ip_without_peer_address(monkeypatch):
    monkeypatch.delenv("OTP_CLIENT_IP_MODE", raising=False)

    assert index_view._get_client_ip(_otp_request()) == ""


def test_legacy_mode_preserves_forwarded_for_rollback(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "legacy")
    request = _otp_request(remote_addr="9.9.9.9", forwarded_for="1.1.1.1, 2.2.2.2")

    assert index_view._get_client_ip(request) == "1.1.1.1"


def test_trusted_proxy_mode_uses_rightmost_untrusted_ip(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "2")
    request = _otp_request(
        remote_addr="10.0.0.3",
        forwarded_for="198.51.100.9, 203.0.113.7, 10.0.0.2",
    )

    assert index_view._get_client_ip(request) == "203.0.113.7"


def test_trusted_proxy_mode_ignores_attacker_prepended_values(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "2")
    request = _otp_request(
        remote_addr="10.0.0.3",
        forwarded_for="192.0.2.66, 203.0.113.7, 10.0.0.2",
    )

    assert index_view._get_client_ip(request) == "203.0.113.7"


def test_trusted_proxy_mode_rejects_attacker_controlled_all_trusted_chain(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "2")
    request = _otp_request(remote_addr="10.0.0.3", forwarded_for="10.9.8.7, 10.0.0.2")

    assert index_view._get_client_ip(request) == "10.0.0.3"


def test_trusted_proxy_mode_rejects_incomplete_hop_inventory(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "2")
    request = _otp_request(
        remote_addr="10.0.0.3",
        forwarded_for="203.0.113.7, 172.16.0.2",
    )

    assert index_view._get_client_ip(request) == "10.0.0.3"


@pytest.mark.parametrize(
    ("trusted_cidrs", "forwarded_for"),
    [
        ("10.0.0.0/8", "198.51.100.9"),
        ("invalid-cidr", "203.0.113.7"),
        ("10.0.0.0/8", "invalid-ip"),
    ],
)
def test_trusted_proxy_mode_fails_safe_to_direct_peer(monkeypatch, trusted_cidrs, forwarded_for):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", trusted_cidrs)
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "1")
    request = _otp_request(remote_addr="192.0.2.8", forwarded_for=forwarded_for)

    assert index_view._get_client_ip(request) == "192.0.2.8"


def test_unknown_mode_fails_safe_to_direct_peer(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "typo")
    request = _otp_request(remote_addr="192.0.2.8", forwarded_for="198.51.100.9")

    assert index_view._get_client_ip(request) == "192.0.2.8"


@pytest.mark.django_db
def test_verify_otp_login_forwards_attributed_ip(monkeypatch):
    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "2")
    request = _otp_request(remote_addr="10.0.0.3", forwarded_for="203.0.113.7, 10.0.0.2")

    with patch.object(index_view, "_create_system_mgmt_client") as mock_client:
        mock_client.return_value.verify_otp_login.return_value = {"result": False}
        index_view.verify_otp_login(request)

    mock_client.return_value.verify_otp_login.assert_called_once_with("ch", "999999", "203.0.113.7")


def test_proxy_users_keep_independent_rate_limit_keys(monkeypatch, locmem_cache):
    from apps.system_mgmt.otp_challenge import check_rate_limit, record_failed_attempt

    monkeypatch.setenv("OTP_CLIENT_IP_MODE", "trusted_proxy")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    monkeypatch.setenv("OTP_TRUSTED_PROXY_HOPS", "1")
    first = _otp_request(remote_addr="10.0.0.3", forwarded_for="203.0.113.7")
    second = _otp_request(remote_addr="10.0.0.3", forwarded_for="203.0.113.8")
    first_ip = index_view._get_client_ip(first)
    second_ip = index_view._get_client_ip(second)

    for _ in range(5):
        record_failed_attempt(first_ip, "alice")

    assert check_rate_limit(first_ip, "alice") == (True, 0)
    assert check_rate_limit(second_ip, "alice") == (False, 5)
