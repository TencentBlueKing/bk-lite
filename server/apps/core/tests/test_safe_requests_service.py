import pydantic.root_model  # noqa

import pytest
import requests

from apps.core.utils import safe_requests as sr
from apps.core.utils.ssrf_validator import SSRFError


def _make_response(*, is_redirect=False, location=None):
    resp = requests.Response()
    resp.status_code = 302 if is_redirect else 200
    if location:
        resp.headers["Location"] = location
    return resp


class TestSafeRequest:
    def test_validates_url_and_returns_response(self, mocker):
        validate = mocker.patch.object(sr.SSRFValidator, "validate", return_value="https://safe.example/api")
        req = mocker.patch.object(sr.requests, "request", return_value=_make_response())

        resp = sr.safe_request("GET", "https://example.com/api", allowlist={"example.com"})

        assert resp.status_code == 200
        validate.assert_called_once_with("https://example.com/api", allowlist={"example.com"})
        # 强制禁用底层自动重定向、注入超时
        _, kwargs = req.call_args
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == 30
        assert req.call_args[0] == ("GET", "https://safe.example/api")

    def test_redirect_blocked_when_not_allowed(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate", return_value="https://safe.example")
        mocker.patch.object(sr.requests, "request", return_value=_make_response(is_redirect=True, location="https://x"))

        with pytest.raises(SSRFError):
            sr.safe_request("GET", "https://example.com", allow_redirects=False)

    def test_redirect_followed_and_revalidated(self, mocker):
        validate = mocker.patch.object(
            sr.SSRFValidator, "validate", side_effect=["https://first", "https://second"]
        )
        first = _make_response(is_redirect=True, location="https://redirect-target")
        second = _make_response()
        req = mocker.patch.object(sr.requests, "request", side_effect=[first, second])

        resp = sr.safe_request("GET", "https://example.com", allow_redirects=True)

        assert resp is second
        # 重定向目标也被校验
        assert validate.call_count == 2
        assert validate.call_args_list[1][0][0] == "https://redirect-target"
        assert req.call_count == 2

    def test_redirect_without_location_breaks(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate", return_value="https://safe")
        resp = _make_response(is_redirect=True)  # no Location header
        mocker.patch.object(sr.requests, "request", return_value=resp)

        out = sr.safe_request("GET", "https://example.com", allow_redirects=True)
        assert out is resp

    def test_request_exception_wrapped(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate", return_value="https://safe")
        mocker.patch.object(sr.requests, "request", side_effect=requests.ConnectionError("boom"))

        with pytest.raises(sr.SafeRequestsError) as exc:
            sr.safe_request("GET", "https://example.com")
        assert "HTTP 请求失败" in str(exc.value)

    def test_verb_helpers_delegate(self, mocker):
        m = mocker.patch.object(sr, "safe_request", return_value="ok")
        assert sr.safe_get("u") == "ok"
        assert sr.safe_post("u") == "ok"
        assert sr.safe_put("u") == "ok"
        assert sr.safe_delete("u") == "ok"
        assert sr.safe_patch("u") == "ok"
        methods = [c.args[0] for c in m.call_args_list]
        assert methods == ["GET", "POST", "PUT", "DELETE", "PATCH"]


class TestSafeRequestLLMEndpoint:
    def test_uses_llm_validator(self, mocker):
        validate = mocker.patch.object(sr.SSRFValidator, "validate_llm_endpoint", return_value="http://10.0.0.5:8000")
        req = mocker.patch.object(sr.requests, "request", return_value=_make_response())

        resp = sr.safe_request_llm_endpoint("POST", "http://10.0.0.5:8000/v1")
        assert resp.status_code == 200
        validate.assert_called_once_with("http://10.0.0.5:8000/v1")
        assert req.call_args[0][1] == "http://10.0.0.5:8000"

    def test_llm_redirect_blocked(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate_llm_endpoint", return_value="http://10.0.0.5")
        mocker.patch.object(sr.requests, "request", return_value=_make_response(is_redirect=True, location="http://x"))
        with pytest.raises(SSRFError):
            sr.safe_request_llm_endpoint("GET", "http://10.0.0.5", allow_redirects=False)

    def test_llm_request_exception_wrapped(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate_llm_endpoint", return_value="http://10.0.0.5")
        mocker.patch.object(sr.requests, "request", side_effect=requests.Timeout("t"))
        with pytest.raises(sr.SafeRequestsError):
            sr.safe_request_llm_endpoint("GET", "http://10.0.0.5")

    def test_llm_verb_helpers(self, mocker):
        m = mocker.patch.object(sr, "safe_request_llm_endpoint", return_value="ok")
        assert sr.safe_get_llm_endpoint("u") == "ok"
        assert sr.safe_post_llm_endpoint("u") == "ok"
        assert [c.args[0] for c in m.call_args_list] == ["GET", "POST"]
