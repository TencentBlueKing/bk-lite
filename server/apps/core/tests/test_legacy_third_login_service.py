import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import override_settings

from apps.core.services import legacy_third_login_service as service


WHITELIST = "bklite.ai,bklite.cn"
TOKEN_SENTINEL = "jwt-token-sentinel-value"
CODE_SENTINEL = "bk-lite-code-sentinel-value"


@pytest.fixture(autouse=True)
def use_dummy_cache_backend(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "legacy-third-login-tests",
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


def _issue(callback_url="https://bklite.ai/playground", token=TOKEN_SENTINEL):
    return service.issue_legacy_third_login_code(token=token, callback_url=callback_url)


@pytest.mark.unit
class TestLegacyCallbackWhitelist:
    def test_empty_whitelist_rejects_all(self):
        with override_settings(LEGACY_THIRD_LOGIN_ALLOWED_CALLBACK_HOSTS=""):
            assert service.is_safe_legacy_external_callback_url("https://bklite.ai/cb") is False

    @pytest.mark.usefixtures("allow_bklite_hosts")
    @pytest.mark.parametrize(
        "callback_url, expected",
        [
            ("https://bklite.ai/playground", True),
            ("https://bklite.cn/playground", True),
            ("HTTPS://BKLITE.AI/playground", True),
            ("https://bklite.ai:8443/playground", True),
            ("http://attacker.example/cb?third_login_code=x", False),
            ("//attacker.com/cb", False),
            ("https://bklite.ai@attacker.com/cb", False),
            ("https://bklite.ai.attacker.com/cb", False),
            ("https://1.2.3.4/cb", False),
            ("javascript:https://bklite.ai", False),
        ],
    )
    def test_host_matching_vectors(self, callback_url, expected):
        assert service.is_safe_legacy_external_callback_url(callback_url) is expected


@pytest.mark.unit
@pytest.mark.usefixtures("allow_bklite_hosts")
class TestLegacyThirdLoginCodeLifecycle:
    def test_issue_exchange_once_then_reject(self):
        code = _issue()
        assert code
        payload = service.consume_legacy_third_login_code(code, "https://bklite.ai")
        assert payload["token"] == TOKEN_SENTINEL
        assert service.consume_legacy_third_login_code(code, "https://bklite.ai") is None

    def test_expired_or_missing_code_is_rejected(self):
        code = _issue()
        cache.delete(f"legacy_third_login_code:{code}")
        assert service.consume_legacy_third_login_code(code, "https://bklite.ai") is None

    def test_callback_host_mismatch_is_rejected_without_consuming(self):
        code = _issue()
        assert service.consume_legacy_third_login_code(code, "https://bklite.cn") is None
        payload = service.consume_legacy_third_login_code(code, "https://bklite.ai")
        assert payload["token"] == TOKEN_SENTINEL

    def test_concurrent_exchange_succeeds_once(self):
        code = _issue()

        def consume():
            return service.consume_legacy_third_login_code(code, "https://bklite.ai")

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: consume(), range(8)))

        successes = [item for item in results if item]
        assert len(successes) == 1
        assert successes[0]["token"] == TOKEN_SENTINEL

    def test_redirect_url_has_code_not_token(self):
        redirect_url = service.authorize_legacy_redirect(
            token=TOKEN_SENTINEL,
            callback_url="https://bklite.ai/playground?third_login_code=old&token=leaked",
            third_login_code="state-code",
        )
        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        assert query["third_login_code"] == ["state-code"]
        assert "bk_lite_code" in query
        assert "token" not in query
        assert TOKEN_SENTINEL not in redirect_url


@pytest.mark.unit
@pytest.mark.usefixtures("allow_bklite_hosts")
class TestLegacyThirdLoginLogs:
    def test_logs_omit_code_and_token_sentinels(self, caplog):
        caplog.set_level(logging.DEBUG, logger="app")
        redirect_url = service.authorize_legacy_redirect(
            token=TOKEN_SENTINEL,
            callback_url="https://bklite.ai/playground",
            third_login_code=CODE_SENTINEL,
        )
        parsed = urlparse(redirect_url)
        issued_code = parse_qs(parsed.query)["bk_lite_code"][0]
        service.consume_legacy_third_login_code(issued_code, "https://bklite.ai")

        rendered = "\n".join(record.getMessage() for record in caplog.records)
        assert TOKEN_SENTINEL not in rendered
        assert CODE_SENTINEL not in rendered
        assert issued_code not in rendered
        assert "https://bklite.ai/playground" not in rendered
        assert "callback_host=bklite.ai" in rendered
        assert "result=success" in rendered
