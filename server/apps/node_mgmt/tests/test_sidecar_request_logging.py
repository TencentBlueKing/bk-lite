import logging
from types import SimpleNamespace

from apps.core.middlewares.request_timing_middleware import RequestTimingMiddleware
from apps.node_mgmt.views import sidecar as sidecar_view


def _messages(caplog, text):
    return [record for record in caplog.records if text in record.getMessage()]


def test_sidecar_success_request_timing_logs_at_debug(caplog):
    caplog.set_level(logging.DEBUG, logger="app")
    middleware = RequestTimingMiddleware(lambda request: None)
    request = SimpleNamespace(method="PUT", path="/api/v1/node_mgmt/open_api/node/sidecars/node-1")
    response = SimpleNamespace(status_code=202)

    middleware._log_request(request, response, 12.5)

    records = _messages(caplog, "Request: PUT /api/v1/node_mgmt/open_api/node/sidecars/node-1")
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG


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


def test_sidecar_update_request_business_log_is_debug(monkeypatch, caplog):
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
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
