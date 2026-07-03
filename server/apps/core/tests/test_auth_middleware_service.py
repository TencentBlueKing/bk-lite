import pydantic.root_model  # noqa

import json

import pytest
from django.conf import settings

from apps.core.middlewares import auth_middleware as am
from apps.core.middlewares.auth_middleware import AuthMiddleware
from apps.core.utils.custom_error import DoesNotExist


class _User:
    def __init__(self, locale="en"):
        self.locale = locale


class _Req:
    def __init__(self, path="/api/v1/cmdb/x/", meta=None, user=None):
        self.path = path
        self.META = meta or {}
        if user is not None:
            self.user = user
        self.session = None


@pytest.fixture
def mw():
    return AuthMiddleware(get_response=lambda r: None)


def _body(resp):
    return json.loads(resp.content)


class TestExtractToken:
    def test_bearer_prefix_stripped(self):
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "Bearer  abc "})
        assert AuthMiddleware._extract_token(req) == "abc"

    def test_plain_token(self):
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "  rawtoken "})
        assert AuthMiddleware._extract_token(req) == "rawtoken"

    def test_missing_header(self):
        assert AuthMiddleware._extract_token(_Req(meta={})) is None


class TestIsExempt:
    def test_view_api_exempt(self, mw):
        view = type("V", (), {"api_exempt": True})()
        assert mw._is_exempt(_Req(), view) is True

    def test_view_login_exempt(self, mw):
        view = type("V", (), {"login_exempt": True})()
        assert mw._is_exempt(_Req(), view) is True

    def test_request_api_pass(self, mw):
        req = _Req()
        req.api_pass = True
        assert mw._is_exempt(req, object()) is True

    def test_exempt_path_prefix(self, mw):
        assert mw._is_exempt(_Req(path="/swagger/index"), object()) is True

    def test_non_exempt_path(self, mw):
        assert mw._is_exempt(_Req(path="/api/v1/cmdb/x/"), object()) is False


class TestProcessView:
    def test_exempt_returns_none(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=True)
        assert mw.process_view(_Req(), object(), [], {}) is None

    def test_missing_token_returns_401(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=False)
        mocker.patch.object(am.LanguageLoader, "__init__", return_value=None)
        mocker.patch.object(am.LanguageLoader, "get", return_value="Please provide Token")
        resp = mw.process_view(_Req(meta={}), object(), [], {})
        assert resp.status_code == 401

    def test_successful_auth_returns_none(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=False)
        user = _User()
        mocker.patch.object(am.auth, "authenticate", return_value=user)
        login = mocker.patch.object(am.auth, "login")
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "tok"})
        # session 需可设置 session_key
        session = mocker.MagicMock()
        session.session_key = "abc"
        req.session = session
        assert mw.process_view(req, object(), [], {}) is None
        login.assert_called_once()

    def test_auth_returns_none_user_401(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=False)
        mocker.patch.object(am.auth, "authenticate", return_value=None)
        mocker.patch.object(am.LanguageLoader, "__init__", return_value=None)
        mocker.patch.object(am.LanguageLoader, "get", return_value="Please provide Token")
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "tok"})
        resp = mw.process_view(req, object(), [], {})
        assert resp.status_code == 401

    def test_does_not_exist_returns_460(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=False)
        mocker.patch.object(am.auth, "authenticate", side_effect=DoesNotExist("nope"))
        mocker.patch.object(am.LanguageLoader, "__init__", return_value=None)
        mocker.patch.object(am.LanguageLoader, "get", return_value="User Does Not Exist")
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "tok"})
        resp = mw.process_view(req, object(), [], {})
        assert resp.status_code == 460

    def test_session_cycle_key_when_no_key(self, mw, mocker):
        mocker.patch.object(mw, "_is_exempt", return_value=False)
        mocker.patch.object(am.auth, "authenticate", return_value=_User())
        mocker.patch.object(am.auth, "login")
        req = _Req(meta={settings.AUTH_TOKEN_HEADER_NAME: "tok"})
        session = mocker.MagicMock()
        session.session_key = None
        req.session = session
        assert mw.process_view(req, object(), [], {}) is None
        session.cycle_key.assert_called_once()


class TestGetLoaderMessage:
    def test_returns_string(self, mocker):
        loader = mocker.MagicMock()
        loader.get.return_value = "msg"
        assert AuthMiddleware._get_loader_message(loader, "k", "def") == "msg"

    def test_non_string_falls_back_to_default(self, mocker):
        loader = mocker.MagicMock()
        loader.get.return_value = {"not": "string"}
        assert AuthMiddleware._get_loader_message(loader, "k", "DEF") == "DEF"


class TestGetLoader:
    def test_uses_user_locale(self, mw, mocker):
        init = mocker.patch.object(am.LanguageLoader, "__init__", return_value=None)
        req = _Req(user=_User(locale="zh-Hans"))
        mw._get_loader(req)
        assert init.call_args.kwargs["default_lang"] == "zh-Hans"

    def test_defaults_to_en_without_user(self, mw, mocker):
        init = mocker.patch.object(am.LanguageLoader, "__init__", return_value=None)
        mw._get_loader(None)
        assert init.call_args.kwargs["default_lang"] == "en"
