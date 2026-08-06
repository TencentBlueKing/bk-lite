from unittest.mock import patch

import pytest
from django.core.cache.backends.locmem import LocMemCache


@pytest.fixture
def service():
    from apps.core.services import login_auth_request_service

    return login_auth_request_service


@pytest.fixture
def local_cache():
    return LocMemCache("login-auth-request-service-tests", {})


@pytest.mark.unit
class TestBrowserBinding:
    def test_create_auth_request_requires_browser_binding_token(self, service):
        with pytest.raises(TypeError):
            service.create_auth_request(
                binding_id=7,
                provider_key="feishu",
                callback_url="/console",
            )

    def test_token_is_signed_unique_and_stored_as_digest(self, service, local_cache):
        browser_binding_token = service.create_browser_binding_token()
        other_browser_binding_token = service.create_browser_binding_token()

        with patch.object(service, "cache", local_cache):
            auth_request = service.create_auth_request(
                binding_id=8,
                provider_key="wechat",
                callback_url="/",
                browser_binding_token=browser_binding_token,
            )

        assert auth_request["browser_binding_hash"] != browser_binding_token
        assert service.validate_browser_binding(auth_request, browser_binding_token) is True
        assert service.validate_browser_binding(auth_request, other_browser_binding_token) is False
        assert service.validate_browser_binding(auth_request, f"{browser_binding_token}tampered") is False
        assert service.validate_browser_binding(auth_request, "") is False

    def test_expired_token_is_rejected(self, service, local_cache):
        issued_at = 1_700_000_000
        with patch.object(service.signing.time, "time", return_value=issued_at):
            browser_binding_token = service.create_browser_binding_token()
            with patch.object(service, "cache", local_cache):
                auth_request = service.create_auth_request(
                    binding_id=8,
                    provider_key="wechat",
                    callback_url="/",
                    browser_binding_token=browser_binding_token,
                )

        with patch.object(
            service.signing.time,
            "time",
            return_value=issued_at + service.AUTH_REQUEST_TTL + 1,
        ):
            assert service.validate_browser_binding(auth_request, browser_binding_token) is False

    def test_pre_deployment_cache_entry_without_digest_remains_compatible(self, service):
        assert service.validate_browser_binding({"status": "pending"}, "") is True

    def test_parallel_requests_use_independent_cookie_names_and_tokens(self, service, local_cache):
        first_token = service.create_browser_binding_token()
        second_token = service.create_browser_binding_token()
        with patch.object(service, "cache", local_cache):
            first_request = service.create_auth_request(
                binding_id=8,
                provider_key="wechat",
                callback_url="/",
                browser_binding_token=first_token,
            )
            second_request = service.create_auth_request(
                binding_id=8,
                provider_key="wechat",
                callback_url="/",
                browser_binding_token=second_token,
            )

        assert service.get_login_auth_browser_cookie_name(first_request["auth_request_id"]) != (
            service.get_login_auth_browser_cookie_name(second_request["auth_request_id"])
        )
        assert service.validate_browser_binding(first_request, first_token) is True
        assert service.validate_browser_binding(second_request, second_token) is True
