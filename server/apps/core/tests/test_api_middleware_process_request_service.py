"""APISecretMiddleware.process_request 全流程单元测试。

补充 test_api_middleware_team_injection 未覆盖的入口逻辑。
仅 mock 真实外部边界（django.contrib.auth、LanguageLoader、settings header 名）。
断言：无 token 放过、认证成功/失败/异常三分支的真实输出与副作用。
"""

from types import SimpleNamespace

import pytest

from apps.core.middlewares import api_middleware as mod
from apps.core.middlewares.api_middleware import APISecretMiddleware

pytestmark = pytest.mark.unit


def _mw():
    return APISecretMiddleware(get_response=lambda r: None)


def _req(token=None, header="HTTP_API_TOKEN"):
    meta = {}
    if token is not None:
        meta[header] = token
    return SimpleNamespace(
        META=meta,
        COOKIES={},
        path="/api/v1/x",
        session=SimpleNamespace(session_key="k"),
        user=SimpleNamespace(group_list=[5], locale="en"),
    )


class TestGetApiToken:
    def test_missing_header_config_returns_none(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", None, create=True)
        assert _mw()._get_api_token(_req(token="abc")) is None

    def test_reads_token_from_configured_header(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", "HTTP_API_TOKEN", create=True)
        req = _req(token="tok123")
        assert _mw()._get_api_token(req) == "tok123"


class TestProcessRequest:
    def test_no_token_sets_api_pass_false_and_passes(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", "HTTP_API_TOKEN", create=True)
        req = _req(token=None)
        assert _mw().process_request(req) is None
        assert req.api_pass is False

    def test_successful_auth_logs_in_and_passes(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", "HTTP_API_TOKEN", create=True)
        user = SimpleNamespace(group_list=[5], locale="en")
        auth = mocker.patch.object(mod, "auth")
        auth.authenticate.return_value = user
        auth.login.return_value = None

        req = _req(token="good")
        result = _mw().process_request(req)
        assert result is None
        assert req.api_pass is True
        auth.login.assert_called_once_with(req, user)

    def test_failed_auth_returns_403(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", "HTTP_API_TOKEN", create=True)
        auth = mocker.patch.object(mod, "auth")
        auth.authenticate.return_value = None

        resp = _mw().process_request(_req(token="bad"))
        assert resp.status_code == 403

    def test_auth_exception_returns_500(self, mocker):
        mocker.patch.object(mod.settings, "API_TOKEN_HEADER_NAME", "HTTP_API_TOKEN", create=True)
        auth = mocker.patch.object(mod, "auth")
        auth.authenticate.side_effect = RuntimeError("auth backend down")

        resp = _mw().process_request(_req(token="x"))
        assert resp.status_code == 500


class TestGetLoader:
    def test_uses_user_locale_when_present(self, mocker):
        captured = {}

        def fake_loader(app, default_lang):
            captured["app"] = app
            captured["lang"] = default_lang
            return object()

        mocker.patch.object(mod, "LanguageLoader", side_effect=fake_loader)
        req = SimpleNamespace(user=SimpleNamespace(locale="zh-cn"))
        _mw()._get_loader(req)
        assert captured == {"app": "core", "lang": "zh-cn"}

    def test_defaults_to_en_without_request(self, mocker):
        captured = {}
        mocker.patch.object(mod, "LanguageLoader", side_effect=lambda app, default_lang: captured.update(lang=default_lang))
        _mw()._get_loader(None)
        assert captured["lang"] == "en"
