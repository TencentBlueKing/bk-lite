from io import BytesIO
from urllib.parse import urlparse

import pydantic.root_model  # noqa
import pytest
import requests

from apps.core.utils import egress_gateway as eg
from apps.core.utils import safe_requests as sr
from apps.core.utils.ssrf_validator import SSRFError, ValidatedTarget


def _make_response(*, is_redirect=False, location=None, status_code=None):
    resp = requests.Response()
    resp.status_code = status_code if status_code is not None else (302 if is_redirect else 200)
    resp._content = b""
    resp._content_consumed = True
    if location:
        resp.headers["Location"] = location
    return resp


def _target(url: str, ip: str = "8.8.8.8") -> ValidatedTarget:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return ValidatedTarget(
        url=url,
        hostname=hostname,
        scheme=parsed.scheme.lower(),
        resolved_ips=(ip,),
        port=parsed.port,
    )


def _patch_session(mocker, *, side_effect=None, return_value=None):
    session = mocker.MagicMock()
    if side_effect is not None:
        session.request.side_effect = side_effect
    else:
        session.request.return_value = return_value if return_value is not None else _make_response()
    mocker.patch.object(eg.requests, "Session", return_value=session)
    return session


class TestSafeRequest:
    @pytest.mark.parametrize(
        ("status_code", "method", "expected_method", "keeps_body"),
        [
            (301, "POST", "GET", False),
            (301, "PUT", "PUT", False),
            (302, "PATCH", "GET", False),
            (303, "DELETE", "GET", False),
            (303, "HEAD", "HEAD", False),
            (307, "POST", "POST", True),
            (308, "PATCH", "PATCH", True),
        ],
    )
    def test_redirect_method_and_body_matrix_from_public_entry(
        self, mocker, status_code, method, expected_method, keeps_body
    ):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://service.example/start"), _target("https://service.example/next")],
        )
        first = _make_response(status_code=status_code, location="https://service.example/next")
        session = _patch_session(mocker, side_effect=[first, _make_response()])

        sr.safe_request(
            method,
            "https://service.example/start",
            allow_redirects=True,
            json={"state": "ready"},
            headers={"Content-Type": "application/json"},
        )

        redirect_call = session.request.call_args_list[1]
        assert redirect_call.args == (expected_method, "https://8.8.8.8/next")
        assert ("json" in redirect_call.kwargs) is keeps_body
        assert ("Content-Type" in redirect_call.kwargs["headers"]) is keeps_body

    def test_validates_url_and_returns_response(self, mocker):
        validate = mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            return_value=_target("https://safe.example/api"),
        )
        session = _patch_session(mocker)

        resp = sr.safe_request("GET", "https://example.com/api", allowlist={"example.com"})

        assert resp.status_code == 200
        validate.assert_called_once_with("https://example.com/api", allowlist={"example.com"})
        _, kwargs = session.request.call_args
        assert kwargs["allow_redirects"] is False
        assert kwargs["timeout"] == 30
        assert session.request.call_args[0] == ("GET", "https://8.8.8.8/api")
        assert kwargs["headers"]["Host"] == "safe.example"

    def test_pins_resolved_ip_and_keeps_original_host(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            return_value=_target("https://evil.example/latest", ip="93.184.216.34"),
        )
        session = _patch_session(mocker)

        sr.safe_request("GET", "https://evil.example/latest")

        method, connect_url = session.request.call_args[0]
        assert method == "GET"
        assert connect_url == "https://93.184.216.34/latest"
        assert session.request.call_args.kwargs["headers"]["Host"] == "evil.example"
        assert session.trust_env is False
        session.mount.assert_any_call("https://", mocker.ANY)
        adapter = session.mount.call_args_list[0][0][1]
        assert adapter.server_hostname == "evil.example"

    def test_direct_mode_drops_caller_proxies(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            return_value=_target("https://safe.example/api"),
        )
        session = _patch_session(mocker)

        sr.safe_request("GET", "https://safe.example/api", proxies={"https": "http://127.0.0.1:8080"})

        assert "proxies" not in session.request.call_args.kwargs

    def test_redirect_blocked_when_not_allowed(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate_target", return_value=_target("https://safe.example"))
        _patch_session(mocker, return_value=_make_response(is_redirect=True, location="https://x"))

        with pytest.raises(SSRFError):
            sr.safe_request("GET", "https://example.com", allow_redirects=False)

    def test_redirect_followed_and_revalidated(self, mocker):
        validate = mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://first"), _target("https://second")],
        )
        first = _make_response(is_redirect=True, location="https://redirect-target")
        second = _make_response()
        session = _patch_session(mocker, side_effect=[first, second])

        resp = sr.safe_request("GET", "https://example.com", allow_redirects=True)

        assert resp is second
        assert validate.call_count == 2
        assert validate.call_args_list[1][0][0] == "https://redirect-target"
        assert session.request.call_count == 2

    def test_relative_redirect_is_resolved_and_intermediate_response_closed(self, mocker):
        validate = mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://service.example/v1/start"), _target("https://service.example/v2/next")],
        )
        first = _make_response(status_code=302, location="../v2/next")
        close = mocker.patch.object(first, "close")
        session = _patch_session(mocker, side_effect=[first, _make_response()])

        sr.safe_request("GET", "https://service.example/v1/start", allow_redirects=True)

        assert validate.call_args_list[1].args[0] == "https://service.example/v2/next"
        assert session.request.call_args_list[1].args == ("GET", "https://8.8.8.8/v2/next")
        close.assert_called_once_with()

    def test_cross_origin_303_uses_get_without_body_or_credentials(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://source.example/start"), _target("https://target.example/next")],
        )
        first = _make_response(status_code=303, location="https://target.example/next")
        session = _patch_session(mocker, side_effect=[first, _make_response()])
        headers = {
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "Host": "source.example",
            "Proxy-Authorization": "Basic proxy-secret",
            "Content-Type": "application/json",
            "X-Request-ID": "request-id",
        }

        sr.safe_request(
            "POST",
            "https://source.example/start",
            allow_redirects=True,
            headers=headers,
            cookies={"session": "secret"},
            json={"action": "charge"},
            params={"source": "tool"},
            auth=("user", "password"),
        )

        redirect_call = session.request.call_args_list[1]
        assert redirect_call.args == ("GET", "https://8.8.8.8/next")
        assert redirect_call.kwargs["headers"]["X-Request-ID"] == "request-id"
        assert redirect_call.kwargs["headers"]["Host"] == "target.example"
        assert "Authorization" not in redirect_call.kwargs["headers"]
        assert "cookies" not in redirect_call.kwargs
        assert "auth" not in redirect_call.kwargs
        assert "json" not in redirect_call.kwargs
        assert "params" not in redirect_call.kwargs
        assert headers["Authorization"] == "Bearer secret"

    def test_307_rewinds_seekable_stream_before_redirect(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://service.example/start"), _target("https://service.example/next")],
        )

        class NonIterableStream:
            def __init__(self, content):
                self._stream = BytesIO(content)

            def read(self):
                return self._stream.read()

            def tell(self):
                return self._stream.tell()

            def seek(self, position):
                return self._stream.seek(position)

        stream = NonIterableStream(b"request-body")
        payloads = []

        def request(method, url, **kwargs):
            payloads.append(kwargs["data"].read())
            if len(payloads) == 1:
                return _make_response(status_code=307, location="https://service.example/next")
            return _make_response()

        _patch_session(mocker, side_effect=request)

        sr.safe_request("POST", "https://service.example/start", allow_redirects=True, data=stream)

        assert payloads == [b"request-body", b"request-body"]

    def test_307_rejects_unrewindable_stream(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://service.example/start"), _target("https://service.example/next")],
        )

        def body():
            yield b"request-body"

        def request(method, url, **kwargs):
            list(kwargs["data"])
            return _make_response(status_code=307, location="https://service.example/next")

        session = _patch_session(mocker, side_effect=request)

        with pytest.raises(sr.SafeRequestsError, match="重定向请求体不可回卷"):
            sr.safe_request("POST", "https://service.example/start", allow_redirects=True, data=body())

        assert session.request.call_count == 1

    def test_same_origin_307_preserves_method_body_and_credentials(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("https://service.example/start"), _target("https://service.example/next")],
        )
        first = _make_response(status_code=307, location="https://service.example/next")
        session = _patch_session(mocker, side_effect=[first, _make_response()])

        sr.safe_request(
            "PUT",
            "https://service.example/start",
            allow_redirects=True,
            headers={"Authorization": "Bearer secret", "Proxy-Authorization": "Basic proxy-secret"},
            cookies={"session": "secret"},
            json={"state": "ready"},
        )

        redirect_call = session.request.call_args_list[1]
        assert redirect_call.args == ("PUT", "https://8.8.8.8/next")
        assert redirect_call.kwargs["headers"]["Authorization"] == "Bearer secret"
        assert "Proxy-Authorization" not in redirect_call.kwargs["headers"]
        assert redirect_call.kwargs["cookies"] == {"session": "secret"}
        assert redirect_call.kwargs["json"] == {"state": "ready"}

    def test_http_to_https_upgrade_keeps_same_host_credentials(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_target",
            side_effect=[_target("http://service.example/start"), _target("https://service.example/next")],
        )
        first = _make_response(status_code=307, location="https://service.example/next")
        session = _patch_session(mocker, side_effect=[first, _make_response()])

        sr.safe_request(
            "GET",
            "http://service.example/start",
            allow_redirects=True,
            headers={"Authorization": "Bearer secret"},
            cookies={"session": "secret"},
        )

        redirect_kwargs = session.request.call_args_list[1].kwargs
        assert redirect_kwargs["headers"]["Authorization"] == "Bearer secret"
        assert redirect_kwargs["cookies"] == {"session": "secret"}

    def test_redirect_without_location_breaks(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate_target", return_value=_target("https://safe"))
        resp = _make_response(is_redirect=True)
        _patch_session(mocker, return_value=resp)

        out = sr.safe_request("GET", "https://example.com", allow_redirects=True)
        assert out is resp

    def test_request_exception_wrapped(self, mocker):
        mocker.patch.object(sr.SSRFValidator, "validate_target", return_value=_target("https://safe"))
        _patch_session(mocker, side_effect=requests.ConnectionError("boom"))

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
        validate = mocker.patch.object(
            sr.SSRFValidator,
            "validate_llm_endpoint_target",
            return_value=_target("http://10.0.0.5:8000/v1", ip="10.0.0.5"),
        )
        session = _patch_session(mocker)

        resp = sr.safe_request_llm_endpoint("POST", "http://10.0.0.5:8000/v1")
        assert resp.status_code == 200
        validate.assert_called_once_with("http://10.0.0.5:8000/v1")
        assert session.request.call_args[0][1] == "http://10.0.0.5:8000/v1"
        assert session.request.call_args.kwargs["headers"]["Host"] == "10.0.0.5:8000"

    def test_llm_redirect_blocked(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_llm_endpoint_target",
            return_value=_target("http://10.0.0.5", ip="10.0.0.5"),
        )
        _patch_session(mocker, return_value=_make_response(is_redirect=True, location="http://x"))
        with pytest.raises(SSRFError):
            sr.safe_request_llm_endpoint("GET", "http://10.0.0.5", allow_redirects=False)

    def test_llm_303_uses_get_without_body(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_llm_endpoint_target",
            side_effect=[
                _target("http://10.0.0.5/v1", ip="10.0.0.5"),
                _target("http://10.0.0.6/v1", ip="10.0.0.6"),
            ],
        )
        first = _make_response(status_code=303, location="http://10.0.0.6/v1")
        session = _patch_session(mocker, side_effect=[first, _make_response()])

        sr.safe_request_llm_endpoint(
            "POST",
            "http://10.0.0.5/v1",
            allow_redirects=True,
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            json={"prompt": "hello"},
        )

        redirect_call = session.request.call_args_list[1]
        assert redirect_call.args == ("GET", "http://10.0.0.6/v1")
        assert "Authorization" not in redirect_call.kwargs["headers"]
        assert "json" not in redirect_call.kwargs

    def test_llm_request_exception_wrapped(self, mocker):
        mocker.patch.object(
            sr.SSRFValidator,
            "validate_llm_endpoint_target",
            return_value=_target("http://10.0.0.5", ip="10.0.0.5"),
        )
        _patch_session(mocker, side_effect=requests.Timeout("t"))
        with pytest.raises(sr.SafeRequestsError):
            sr.safe_request_llm_endpoint("GET", "http://10.0.0.5")

    def test_llm_verb_helpers(self, mocker):
        m = mocker.patch.object(sr, "safe_request_llm_endpoint", return_value="ok")
        assert sr.safe_get_llm_endpoint("u") == "ok"
        assert sr.safe_post_llm_endpoint("u") == "ok"
        assert [c.args[0] for c in m.call_args_list] == ["GET", "POST"]
