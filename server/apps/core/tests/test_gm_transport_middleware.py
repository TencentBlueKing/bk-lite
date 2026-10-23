import json
import logging
import threading
import traceback

import pytest
from django.http import HttpResponse, StreamingHttpResponse
from django.test import RequestFactory, override_settings

from apps.core.logger import SafeLogException
from apps.core.middlewares.gm_transport_middleware import GmTransportMiddleware
from apps.core.services.gm_transport import NONCE_KEY, install_plaintext, reset_degrade_state
from apps.core.tests.test_gm_transport_envelope import BODY, KID, NONCE, PRIVATE_KEY, REQUEST_VECTOR, SM4_KEY, TS
from apps.core.utils.crypto.gm_transport import GmTransportCryptoError, open_response_envelope, public_key_hex_from_private, seal_request_envelope

PLAINTEXT_SENTINEL = "PLAINTEXT_SENTINEL_9f3a"
QUERY_SENTINEL = "QUERY_SENTINEL_9f3a"
LOCALE_HEADER = {"HTTP_X_BK_LOCALE": "zh-Hans"}


class NxCache:
    def __init__(self):
        self._lock = threading.Lock()
        self.store = {}
        self.now = 0.0
        self.timeouts = []

    def add(self, key, value, timeout=None):
        with self._lock:
            self._expire()
            self.timeouts.append(timeout)
            if key in self.store:
                return False
            self.store[key] = self.now + float(timeout or 0)
            return True

    def advance(self, seconds):
        with self._lock:
            self.now += seconds
            self._expire()

    def _expire(self):
        dead = [key for key, expiry in self.store.items() if expiry <= self.now]
        for key in dead:
            del self.store[key]

    def __contains__(self, item):
        with self._lock:
            self._expire()
            return item in self.store


@pytest.fixture
def gm(monkeypatch):
    store = NxCache()
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.server_now_ms", lambda: TS)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    monkeypatch.setattr("apps.core.services.gm_transport.cache", store)
    reset_degrade_state()
    yield store
    reset_degrade_state()


def _envelope(method="POST", path="/core/api/login/", query="", body=b"{}", cty="application/json", nonce=None, ts=TS, **overrides):
    envelope = seal_request_envelope(
        public_key_hex=public_key_hex_from_private(PRIVATE_KEY),
        sm4_key=SM4_KEY,
        iv=bytes.fromhex("000102030405060708090a0b0c0d0e0f"),
        nonce=nonce or NONCE,
        ts=ts,
        method=method,
        path=path,
        cty=cty,
        query=query,
        body=body,
    )
    envelope.update(overrides)
    return envelope


def _request(envelope, wire="POST", path="/api/v1/core/api/login/", header="1"):
    raw = json.dumps(envelope).encode("utf-8")
    request = RequestFactory().generic(wire, path, data=raw, content_type="application/json", **LOCALE_HEADER)
    if header is not None:
        request.META["HTTP_X_GM_TRANSPORT"] = header
    return request


def _run(request, view):
    return GmTransportMiddleware(view)(request)


def _json(response):
    return json.loads(response.content)


def _nonce_key(nonce=NONCE):
    return NONCE_KEY.format(nonce=nonce)


def test_middleware_is_mounted_after_security():
    from django.conf import settings

    names = list(settings.MIDDLEWARE)
    security = names.index("django.middleware.security.SecurityMiddleware")
    assert names[security + 1] == "apps.core.middlewares.gm_transport_middleware.GmTransportMiddleware"


def test_plaintext_without_header_reaches_the_view(gm):
    seen = {}

    def view(request):
        seen["method"] = request.method
        seen["body"] = request.body
        return HttpResponse(b"plain-ok")

    request = RequestFactory().post("/api/v1/core/api/login/", data=b'{"username":"admin"}', content_type="application/json")
    response = _run(request, view)
    assert response.content == b"plain-ok"
    assert seen == {"method": "POST", "body": b'{"username":"admin"}'}
    assert "X-Gm-Transport" not in response
    assert _nonce_key() not in gm


def test_non_api_and_public_paths_pass_through(gm):
    def view(request):
        return HttpResponse(request.body)

    for path in ("/openapi/v1/core/api/login/", "/api/v1/core/api/gm_transport_public/"):
        request = _request({"v": 1}, path=path)
        response = _run(request, view)
        assert response.content == json.dumps({"v": 1}).encode("utf-8")


def test_frozen_vector_roundtrip_restores_query_body_and_encrypts_response(gm):
    seen = {}

    def view(request):
        seen["name"] = request.GET["name"]
        seen["q"] = request.GET["q"]
        seen["body"] = request.body
        seen["method"] = request.method
        response = HttpResponse(b'{"result":true}', content_type="application/json")
        response["X-Trace"] = "keep"
        return response

    response = _run(_request(dict(REQUEST_VECTOR)), view)
    assert seen == {"name": "a", "q": "中文", "body": BODY, "method": "POST"}
    assert response.status_code == 200
    assert response["X-Gm-Transport"] == "1"
    assert response["X-Trace"] == "keep"
    assert response["Content-Type"].startswith("application/json")
    opened = open_response_envelope(
        _json(response),
        SM4_KEY,
        expected_nonce=NONCE,
        expected_seq=1,
        expected_status=200,
    )
    assert opened == b'{"result":true}'
    assert _nonce_key() in gm


def test_get_on_post_is_rewritten_and_other_methods_must_match(gm):
    seen = {}

    def view(request):
        seen["method"] = request.method
        seen["wire"] = request.META["REQUEST_METHOD"]
        seen["page"] = request.GET["page"]
        seen["q"] = request.GET["q"]
        return HttpResponse(b"list")

    envelope = _envelope(method="GET", path="/cmdb/api/instances/", query="page=1&q=中文", body=b"")
    response = _run(_request(envelope, wire="POST", path="/api/v1/cmdb/api/instances/?ignored=1"), view)
    assert response.status_code == 200
    assert seen["method"] == "GET"
    assert seen["wire"] == "GET"
    assert seen["page"] == "1"
    assert seen["q"] == "中文"

    def forbidden(request):
        raise AssertionError("view ran")

    rejected = _run(_request(_envelope(method="DELETE"), wire="POST"), forbidden)
    assert rejected.status_code == 400
    assert _json(rejected)["code"] == "gm_transport_rejected"


def test_head_is_not_rewritten(gm):
    def view(request):
        raise AssertionError("view ran")

    response = _run(_request(_envelope(method="GET", body=b""), wire="HEAD"), view)
    assert response.status_code == 400
    assert _json(response)["code"] == "gm_transport_rejected"


def test_bad_mac_does_not_occupy_nonce_and_logs_without_secrets(gm, caplog):
    def view(request):
        raise AssertionError("view ran")

    bad = _envelope(query=QUERY_SENTINEL, body=PLAINTEXT_SENTINEL.encode())
    bad["mac"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    with caplog.at_level(logging.DEBUG, logger="app"):
        response = _run(_request(bad), view)
    assert response.status_code == 400
    assert _json(response)["code"] == "gm_transport_rejected"
    assert _nonce_key() not in gm
    record = caplog.records[-1]
    assert record.levelno == logging.WARNING
    assert record.msg == "event=gm_transport_rejected path=%s kid=%s error_type=%s"
    assert record.args[2] == "gm_transport_rejected"
    assert record.exc_info is None
    rendered = "\n".join(item.getMessage() for item in caplog.records)
    assert PLAINTEXT_SENTINEL not in rendered
    assert QUERY_SENTINEL not in rendered
    assert PRIVATE_KEY not in rendered
    assert NONCE not in rendered

    def ok(request):
        return HttpResponse(b"ok")

    second = _run(_request(_envelope(query=QUERY_SENTINEL, body=PLAINTEXT_SENTINEL.encode())), ok)
    assert second.status_code == 200


def test_expired_request_does_not_occupy_nonce(gm):
    def view(request):
        raise AssertionError("view ran")

    response = _run(_request(_envelope(ts=TS - 300_001)), view)
    assert response.status_code == 400
    assert _json(response)["code"] == "gm_transport_expired"
    assert _nonce_key() not in gm


def test_replay_and_ttl_cover_the_rest_of_the_window(gm, monkeypatch):
    calls = {"count": 0}

    def view(request):
        calls["count"] += 1
        return HttpResponse(b"ok")

    future = TS + 299_000
    monkeypatch.setattr("apps.core.services.gm_transport.server_now_ms", lambda: TS)
    envelope = _envelope(ts=future, nonce="aabbccddeeff00112233445566778899")
    assert _run(_request(envelope), view).status_code == 200
    assert gm.timeouts[-1] == 599
    gm.advance(301)
    replay = _run(_request(envelope), view)
    assert replay.status_code == 400
    assert _json(replay)["code"] == "gm_transport_replay"
    assert calls["count"] == 1


def test_decrypt_failure_keeps_the_nonce(gm, monkeypatch):
    def broken(*args, **kwargs):
        raise GmTransportCryptoError("padding")

    monkeypatch.setattr("apps.core.services.gm_transport.decrypt_sm4_cbc", broken)

    def view(request):
        raise AssertionError("view ran")

    response = _run(_request(_envelope()), view)
    assert response.status_code == 400
    assert _nonce_key() in gm
    monkeypatch.undo()
    monkeypatch.setattr("apps.core.services.gm_transport.cache", gm)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.server_now_ms", lambda: TS)
    replay = _run(_request(_envelope()), view)
    assert _json(replay)["code"] == "gm_transport_replay"


def test_missing_key_kid_mismatch_and_locmem_do_not_run_the_view(gm, monkeypatch):
    def view(request):
        raise AssertionError("view ran")

    monkeypatch.delenv("GM_SM2_PRIVATE_KEY", raising=False)
    missing = _run(_request(_envelope(nonce="11111111111111111111111111111111")), view)
    assert missing.status_code == 503
    assert _json(missing)["code"] == "gm_transport_unavailable"
    assert _nonce_key("11111111111111111111111111111111") not in gm

    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    mismatch = _envelope(nonce="22222222222222222222222222222222")
    mismatch["kid"] = "0000000000000000"
    rejected = _run(_request(mismatch), view)
    assert rejected.status_code == 400
    assert _json(rejected)["code"] == "gm_transport_rejected"
    assert _nonce_key("22222222222222222222222222222222") not in gm

    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: False)
    unavailable = _run(_request(_envelope(nonce="33333333333333333333333333333333")), view)
    assert unavailable.status_code == 503
    assert _nonce_key("33333333333333333333333333333333") not in gm


def test_content_length_over_280mib_is_rejected_without_a_nonce(gm):
    def view(request):
        raise AssertionError("view ran")

    request = _request(_envelope())
    request.META["CONTENT_LENGTH"] = str(280 * 1024 * 1024 + 1)
    response = _run(request, view)
    assert response.status_code == 413
    assert _json(response)["code"] == "gm_transport_too_large"
    assert _nonce_key() not in gm


def test_envelope_over_django_body_limit_restores_a_readable_plaintext(gm):
    plaintext = b"x" * (2 * 1024 * 1024)
    envelope = _envelope(body=plaintext, nonce="44444444444444444444444444444444")
    raw = json.dumps(envelope).encode("utf-8")
    assert len(raw) > 2_621_440
    seen = {}

    def view(request):
        seen["body"] = request.body
        seen["length"] = request.META["CONTENT_LENGTH"]
        return HttpResponse(b"ok")

    response = _run(_request(envelope, path="/api/v1/core/api/login/"), view)
    assert response.status_code == 200
    assert seen["body"] == plaintext
    assert seen["length"] == str(len(plaintext))


def test_empty_and_no_content_responses_stay_plaintext(gm):
    def empty(request):
        return HttpResponse(b"", content_type="application/json")

    def no_content(request):
        return HttpResponse(status=204)

    empty_response = _run(_request(_envelope(nonce="55555555555555555555555555555555")), empty)
    assert empty_response.content == b""
    assert "X-Gm-Transport" not in empty_response
    no_content_response = _run(_request(_envelope(nonce="66666666666666666666666666666666")), no_content)
    assert no_content_response.status_code == 204
    assert "X-Gm-Transport" not in no_content_response


def test_oversized_plaintext_response_is_not_returned(gm, monkeypatch):
    monkeypatch.setattr("apps.core.services.gm_transport.MAX_RESPONSE_BYTES", 4)

    def view(request):
        return HttpResponse(b"business-secret-body", content_type="application/json")

    response = _run(_request(_envelope(nonce="77777777777777777777777777777777")), view)
    assert response.status_code == 413
    assert _json(response)["code"] == "gm_transport_too_large"
    assert b"business-secret-body" not in response.content
    assert "X-Gm-Transport" not in response


def test_non_json_response_stays_plaintext(gm):
    def view(request):
        return HttpResponse(b"<html>secret</html>", content_type="text/html")

    response = _run(_request(_envelope(nonce="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee")), view)
    assert response.status_code == 200
    assert response.content == b"<html>secret</html>"
    assert "X-Gm-Transport" not in response


def test_problem_json_response_is_sealed(gm):
    def view(request):
        return HttpResponse(b'{"result":false}', content_type="application/problem+json", status=400)

    response = _run(_request(_envelope(nonce="ffffffffffffffffffffffffffffffff")), view)
    assert response.status_code == 400
    assert response["X-Gm-Transport"] == "1"
    assert b'{"result":false}' not in response.content


def test_streaming_response_stays_plaintext(gm):
    def view(request):
        return StreamingHttpResponse(iter([b"data: hello\n\n"]), content_type="text/event-stream")

    response = _run(_request(_envelope(nonce="88888888888888888888888888888888")), view)
    assert response["Content-Type"].startswith("text/event-stream")
    assert "X-Gm-Transport" not in response
    assert b"".join(response.streaming_content) == b"data: hello\n\n"


def test_unexpected_failure_logs_one_traceback_without_the_exception_text(gm, monkeypatch, caplog):
    caught = {}
    secret = "SECRET_TRACE_SENTINEL"

    def boom(request):
        try:
            raise RuntimeError(secret)
        except RuntimeError as exc:
            caught["error"] = exc
            raise

    monkeypatch.setattr("apps.core.middlewares.gm_transport_middleware.open_request", boom)
    with caplog.at_level(logging.DEBUG, logger="app"):
        response = _run(_request(_envelope()), lambda request: HttpResponse(b"nope"))
    assert response.status_code == 500
    assert b"SECRET_TRACE_SENTINEL" not in response.content
    traced = [record for record in caplog.records if record.exc_info]
    assert len(traced) == 1
    assert traced[0].msg == "event=gm_transport_failed path=%s failed_stage=%s error_type=%s"
    assert traced[0].args[1:] == ("open_request", "RuntimeError")
    assert traced[0].exc_info[0] is SafeLogException
    assert str(traced[0].exc_info[1]) == "RuntimeError"
    assert traced[0].exc_info[2] is caught["error"].__traceback__
    assert str(caught["error"]) == "SECRET_TRACE_SENTINEL"
    formatted = "".join(traceback.format_exception(*traced[0].exc_info))
    assert "boom" in [frame.name for frame in traceback.extract_tb(traced[0].exc_info[2])]
    rendered = "\n".join(item.getMessage() for item in caplog.records) + formatted
    assert "SECRET_TRACE_SENTINEL" not in rendered
    assert PRIVATE_KEY not in rendered
    assert KID not in traced[0].getMessage()


def test_install_plaintext_failure_logs_one_traceback_and_skips_the_view(gm, monkeypatch, caplog):
    caught = {}
    secret = "INSTALL_PLAINTEXT_SENTINEL"
    nonce = "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"

    def boom(request, opened):
        try:
            raise RuntimeError(secret)
        except RuntimeError as exc:
            caught["error"] = exc
            raise

    monkeypatch.setattr("apps.core.middlewares.gm_transport_middleware.install_plaintext", boom)

    def view(request):
        raise AssertionError("view ran")

    with caplog.at_level(logging.DEBUG, logger="app"):
        response = _run(_request(_envelope(nonce=nonce)), view)
    assert response.status_code == 500
    assert _json(response)["code"] == "system_error"
    assert secret.encode() not in response.content
    traced = [record for record in caplog.records if record.exc_info]
    assert len(traced) == 1
    assert traced[0].msg == "event=gm_transport_failed path=%s failed_stage=%s error_type=%s"
    assert traced[0].args[1:] == ("install_plaintext", "RuntimeError")
    assert traced[0].exc_info[0] is SafeLogException
    assert str(traced[0].exc_info[1]) == "RuntimeError"
    assert traced[0].exc_info[2] is caught["error"].__traceback__
    formatted = "".join(traceback.format_exception(*traced[0].exc_info))
    rendered = "\n".join(item.getMessage() for item in caplog.records) + formatted
    assert secret not in rendered
    assert PRIVATE_KEY not in rendered

    monkeypatch.setattr("apps.core.middlewares.gm_transport_middleware.install_plaintext", install_plaintext)
    again = _run(_request(_envelope(nonce=nonce)), view)
    assert again.status_code == 400
    assert _json(again)["code"] == "gm_transport_replay"


def test_cache_add_failure_is_unavailable(gm, monkeypatch, caplog):
    caught = []

    def broken_add(*args, **kwargs):
        exc = ConnectionError("redis://REDIS_PASSWORD_SENTINEL")
        caught.append(exc)
        raise exc

    monkeypatch.setattr(gm, "add", broken_add)

    def view(request):
        raise AssertionError("view ran")

    first_nonce = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    with caplog.at_level(logging.DEBUG, logger="app"):
        response = _run(_request(_envelope(nonce=first_nonce)), view)
        again = _run(_request(_envelope(nonce="dddddddddddddddddddddddddddddddd")), view)
    assert response.status_code == 503
    assert again.status_code == 503
    assert _json(response)["code"] == "gm_transport_unavailable"
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == "event=gm_transport_degraded failed_stage=%s error_type=gm_transport_unavailable"
    assert errors[0].args == ("cache",)
    assert errors[0].exc_info[0] is SafeLogException
    assert str(errors[0].exc_info[1]) == "ConnectionError"
    assert errors[0].exc_info[2] is caught[0].__traceback__
    assert str(caught[0]) == "redis://REDIS_PASSWORD_SENTINEL"
    formatted = "".join(traceback.format_exception(*errors[0].exc_info))
    rendered = "\n".join(record.getMessage() for record in caplog.records) + formatted
    assert "REDIS_PASSWORD_SENTINEL" not in rendered
    assert first_nonce not in rendered
    assert PRIVATE_KEY not in rendered
    assert any(record.levelno == logging.DEBUG and record.args == ("cache",) for record in caplog.records)


def test_two_same_envelopes_admit_only_one(gm):
    calls = {"count": 0}
    barrier = threading.Barrier(2)

    def view(request):
        calls["count"] += 1
        return HttpResponse(b"ok")

    envelope = _envelope(nonce="cccccccccccccccccccccccccccccccc")
    results = []

    def run():
        barrier.wait()
        results.append(_run(_request(envelope), view))

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(item.status_code for item in results) == [200, 400]
    assert calls["count"] == 1


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "gm-transport-unavailable",
        }
    }
)
def test_real_locmem_backend_is_unavailable(monkeypatch):
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.server_now_ms", lambda: TS)

    def view(request):
        raise AssertionError("view ran")

    response = _run(_request(_envelope(nonce="dddddddddddddddddddddddddddddddd")), view)
    assert response.status_code == 503
    assert _json(response)["code"] == "gm_transport_unavailable"
