import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import RequestFactory, override_settings

from apps.core.views import index_view


WHITELIST = "bklite.ai,bklite.cn"
TOKEN_SENTINEL = "jwt-token-sentinel-value"


def _json(response):
    return json.loads(response.content)


@pytest.fixture(autouse=True)
def use_dummy_cache_backend(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "legacy-third-login-view-tests",
        }
    }
    from django.core.cache import caches

    caches.close_all()
    yield
    caches.close_all()


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def allow_bklite_hosts(settings):
    settings.LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS = WHITELIST


def _authorize_request(payload, token=TOKEN_SENTINEL):
    request = RequestFactory().post(
        "/api/v1/core/api/legacy_third_login/authorize/",
        data=json.dumps(payload),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {token}",
    )
    request.user = MagicMock(is_authenticated=True)
    return request


def _exchange_request(payload, origin="https://bklite.ai"):
    headers = {"HTTP_ORIGIN": origin} if origin else {}
    request = RequestFactory().post(
        "/api/v1/core/api/legacy_third_login/exchange/",
        data=json.dumps(payload),
        content_type="application/json",
        **headers,
    )
    return request


@pytest.mark.unit
class TestLegacyThirdLoginAuthorizeView:
    def test_empty_whitelist_returns_400(self):
        with override_settings(LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=""):
            response = index_view.legacy_third_login_authorize(
                _authorize_request(
                    {
                        "callback_url": "https://bklite.ai/playground",
                        "third_login_code": "state",
                    }
                )
            )
        assert response.status_code == 400
        assert "redirect_url" not in _json(response)

    @pytest.mark.usefixtures("allow_bklite_hosts")
    def test_whitelisted_hosts_return_redirect_without_token(self):
        for host in ("bklite.ai", "bklite.cn"):
            response = index_view.legacy_third_login_authorize(
                _authorize_request(
                    {
                        "callback_url": f"https://{host}/playground?third_login_code=old",
                        "third_login_code": "state",
                    }
                )
            )
            assert response.status_code == 200
            redirect_url = _json(response)["redirect_url"]
            query = parse_qs(urlparse(redirect_url).query)
            assert query["third_login_code"] == ["state"]
            assert query["bk_lite_code"]
            assert "token" not in query
            assert TOKEN_SENTINEL not in redirect_url

    @pytest.mark.usefixtures("allow_bklite_hosts")
    def test_non_whitelisted_host_returns_400(self):
        response = index_view.legacy_third_login_authorize(
            _authorize_request(
                {
                    "callback_url": "http://attacker.example/cb?third_login_code=x",
                    "third_login_code": "x",
                }
            )
        )
        assert response.status_code == 400

    def test_missing_bearer_token_returns_401(self):
        request = RequestFactory().post(
            "/api/v1/core/api/legacy_third_login/authorize/",
            data=json.dumps({"callback_url": "https://bklite.ai/playground", "third_login_code": "state"}),
            content_type="application/json",
        )
        response = index_view.legacy_third_login_authorize(request)
        assert response.status_code == 401


@pytest.mark.unit
@pytest.mark.usefixtures("allow_bklite_hosts")
class TestLegacyThirdLoginExchangeView:
    def test_exchange_success_then_reuse_fails(self):
        authorize = index_view.legacy_third_login_authorize(
            _authorize_request(
                {
                    "callback_url": "https://bklite.ai/playground",
                    "third_login_code": "state",
                }
            )
        )
        code = parse_qs(urlparse(_json(authorize)["redirect_url"]).query)["bk_lite_code"][0]
        first = index_view.legacy_third_login_exchange(_exchange_request({"code": code}))
        assert first.status_code == 200
        assert _json(first) == {"result": True, "data": {"token": TOKEN_SENTINEL}}
        second = index_view.legacy_third_login_exchange(_exchange_request({"code": code}))
        assert second.status_code == 400
        assert _json(second)["message"] == "Invalid or expired code"

    def test_cors_preflight_allows_both_site_origins(self):
        for origin in ("https://bklite.ai", "https://bklite.cn"):
            request = RequestFactory().generic(
                "OPTIONS",
                "/api/v1/core/api/legacy_third_login/exchange/",
                HTTP_ORIGIN=origin,
            )
            response = index_view.legacy_third_login_exchange(request)
            assert response.status_code == 200
            assert response["Access-Control-Allow-Origin"] == origin
            assert "POST" in response["Access-Control-Allow-Methods"]

    def test_cors_preflight_rejects_unknown_origin(self):
        request = RequestFactory().generic(
            "OPTIONS",
            "/api/v1/core/api/legacy_third_login/exchange/",
            HTTP_ORIGIN="https://attacker.example",
        )
        response = index_view.legacy_third_login_exchange(request)
        assert "Access-Control-Allow-Origin" not in response


def _bound_auth_request(auth_request_id, extra=None):
    from apps.core.services.login_auth_request_service import (
        create_browser_binding_token,
        _hash_browser_binding_token,
    )

    origin_token = create_browser_binding_token()
    auth_request = {
        "auth_request_id": auth_request_id,
        "status": "pending",
        "browser_binding_hash": _hash_browser_binding_token(origin_token),
        "legacy_external_callback_url": "",
        "legacy_third_login_code": "",
    }
    if extra:
        auth_request.update(extra)
    return auth_request, origin_token


@pytest.mark.unit
@pytest.mark.usefixtures("allow_bklite_hosts")
class TestLoginAuthCallbackLegacyRedirect:
    @patch("apps.core.views.index_view.get_auth_request")
    @patch("apps.core.views.index_view.parse_auth_request_state")
    @patch("apps.core.views.index_view.SystemMgmt")
    @patch("apps.core.views.index_view.update_auth_request_status")
    def test_login_auth_callback_returns_legacy_redirect_url(
        self,
        mock_update_status,
        mock_system_mgmt,
        mock_parse_state,
        mock_get_auth_request,
    ):
        mock_parse_state.return_value = {
            "auth_request_id": "auth-legacy",
            "binding_id": 5,
            "callback_url": "/",
        }
        auth_request, origin_token = _bound_auth_request(
            "auth-legacy",
            {
                "legacy_external_callback_url": "https://bklite.ai/playground?third_login_code=legacy-code",
                "legacy_third_login_code": "legacy-code",
            },
        )
        mock_get_auth_request.return_value = auth_request
        mock_system_mgmt.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"id": 9, "username": "legacy-user", "token": "binding-token"},
        }

        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-legacy"] = origin_token
        response = index_view.login_auth_callback(request)

        assert response.status_code == 302
        login_result = mock_update_status.call_args.kwargs["login_result"]
        redirect_url = login_result["legacy_redirect_url"]
        query = parse_qs(urlparse(redirect_url).query)
        assert query["third_login_code"] == ["legacy-code"]
        assert query["bk_lite_code"]
        assert "token" not in query
        assert "binding-token" not in redirect_url
        assert "legacy_external_callback_url" not in login_result
        assert "legacy_third_login_code" not in login_result

    @patch("apps.core.views.index_view.get_auth_request")
    @patch("apps.core.views.index_view.parse_auth_request_state")
    @patch("apps.core.views.index_view.SystemMgmt")
    @patch("apps.core.views.index_view.update_auth_request_status")
    def test_login_auth_callback_ignores_cached_non_whitelisted_legacy_url(
        self,
        mock_update_status,
        mock_system_mgmt,
        mock_parse_state,
        mock_get_auth_request,
    ):
        mock_parse_state.return_value = {
            "auth_request_id": "auth-legacy-stale",
            "binding_id": 5,
            "callback_url": "/",
        }
        auth_request, origin_token = _bound_auth_request(
            "auth-legacy-stale",
            {
                "legacy_external_callback_url": "https://attacker.example/cb?third_login_code=legacy-code",
                "legacy_third_login_code": "legacy-code",
            },
        )
        mock_get_auth_request.return_value = auth_request
        mock_system_mgmt.return_value.login_with_binding.return_value = {
            "result": True,
            "data": {"id": 9, "username": "legacy-user", "token": "binding-token"},
        }

        request = RequestFactory().get("/api/v1/core/api/login_auth/callback/?state=signed&code=auth-code")
        request.COOKIES["bklite_login_auth_browser_auth-legacy-stale"] = origin_token
        response = index_view.login_auth_callback(request)

        assert response.status_code == 302
        login_result = mock_update_status.call_args.kwargs["login_result"]
        assert "legacy_redirect_url" not in login_result
        assert "legacy_external_callback_url" not in login_result


@pytest.mark.unit
class TestStartLoginAuthLegacyWhitelist:
    def test_rejects_when_whitelist_empty(self):
        with override_settings(LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=""):
            request = RequestFactory().post(
                "/api/v1/core/api/start_login_auth/",
                data=json.dumps(
                    {
                        "binding_id": 5,
                        "callback_url": "/",
                        "legacy_external_callback_url": "https://bklite.ai/playground?third_login_code=legacy-code",
                        "legacy_third_login_code": "legacy-code",
                    }
                ),
                content_type="application/json",
            )
            response = index_view.start_login_auth(request)
        assert response.status_code == 400
        assert _json(response)["message"] == "legacy_external_callback_url is not allowed"

    def test_rejects_non_whitelisted_host(self):
        with override_settings(LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=WHITELIST):
            request = RequestFactory().post(
                "/api/v1/core/api/start_login_auth/",
                data=json.dumps(
                    {
                        "binding_id": 5,
                        "callback_url": "/",
                        "legacy_external_callback_url": "https://attacker.example/cb?third_login_code=x",
                        "legacy_third_login_code": "x",
                    }
                ),
                content_type="application/json",
            )
            response = index_view.start_login_auth(request)
        assert response.status_code == 400
        assert _json(response)["message"] == "legacy_external_callback_url is not allowed"

