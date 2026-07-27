import logging
from types import SimpleNamespace

from apps.core.middlewares.request_timing_middleware import RequestTimingMiddleware
from apps.node_mgmt.utils import token_auth
from apps.node_mgmt.views import sidecar as sidecar_view
from config.components.log import SuppressSuccessfulSidecarAccessLogs


def _messages(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def test_sidecar_success_request_timing_is_suppressed(caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    middleware = RequestTimingMiddleware(lambda request: None)
    request = SimpleNamespace(method="PUT", path="/api/v1/node_mgmt/open_api/node/sidecars/node-1")
    response = SimpleNamespace(status_code=202)

    middleware._log_request(request, response, 12.5)

    records = _messages(caplog, "Request: PUT /api/v1/node_mgmt/open_api/node/sidecars/node-1")
    assert records == []


def test_sidecar_error_request_timing_keeps_warning_level(caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    middleware = RequestTimingMiddleware(lambda request: None)
    request = SimpleNamespace(method="GET", path="/node_mgmt/open_api/node/sidecar/collectors")
    response = SimpleNamespace(status_code=401)

    middleware._log_request(request, response, 8.0)

    records = _messages(caplog, "Request: GET /node_mgmt/open_api/node/sidecar/collectors")
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING


def test_sidecar_slow_request_timing_keeps_warning_level(caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    middleware = RequestTimingMiddleware(lambda request: None)
    request = SimpleNamespace(method="GET", path="/api/v1/node_mgmt/open_api/node/sidecar/collectors")
    response = SimpleNamespace(status_code=200)

    middleware._log_request(request, response, middleware.SLOW_REQUEST_THRESHOLD_MS + 1)

    records = _messages(caplog, "Slow Request: GET /api/v1/node_mgmt/open_api/node/sidecar/collectors")
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING


def test_sidecar_update_request_has_no_success_business_log(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="node")
    monkeypatch.setattr(sidecar_view, "check_token_auth", lambda node_id, request: None)
    monkeypatch.setattr(sidecar_view.Sidecar, "update_node_client", lambda request, node_id: {"ok": True})
    request = SimpleNamespace(
        data={
            "node_name": "node-1",
            "node_details": {
                "ip": "10.0.0.1",
            },
        }
    )

    response = sidecar_view.OpenSidecarViewSet().update_sidecar_client(request, "node-1")

    assert response == {"ok": True}
    records = _messages(caplog, "Received sidecar node update request node_id=node-1")
    assert records == []


def test_successful_token_auth_has_no_success_log(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="node")
    monkeypatch.setattr(token_auth, "get_client_token", lambda request: "token")
    monkeypatch.setattr(token_auth, "decode_token", lambda token, node_id: {"node_id": node_id})
    monkeypatch.setattr(token_auth, "get_node_cache_token", lambda node_id: "token")

    token_auth.check_token_auth("node-1", SimpleNamespace())

    assert _messages(caplog, "Sidecar认证成功") == []


def _uvicorn_access_record(path, status_code):
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("172.20.0.18:40278", "GET", path, "1.1", status_code),
        exc_info=None,
    )


def test_uvicorn_access_filter_suppresses_successful_sidecar_request():
    record = _uvicorn_access_record(
        "/api/v1/node_mgmt/open_api/node/sidecar/collectors?node_id=node-1",
        304,
    )

    assert SuppressSuccessfulSidecarAccessLogs().filter(record) is False


def test_uvicorn_access_filter_keeps_failed_sidecar_request():
    record = _uvicorn_access_record("/api/v1/node_mgmt/open_api/node/sidecar/collectors", 500)

    assert SuppressSuccessfulSidecarAccessLogs().filter(record) is True


def test_uvicorn_access_filter_keeps_other_successful_request():
    record = _uvicorn_access_record("/api/v1/core/users", 200)

    assert SuppressSuccessfulSidecarAccessLogs().filter(record) is True
