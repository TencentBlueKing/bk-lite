import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from apps.rum.services.analytics import UnavailableAnalytics, get_analytics, set_analytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.health import REASON_ANALYTICS, REASON_CONTROL, probe_pipeline_health, resolve_product_scope
from apps.rum.services.query import apply_degradation, empty_release_list, empty_session_list
from apps.rum.services.settings import RumRuntimeSettings

pytestmark = pytest.mark.django_db


def _settings(**overrides) -> RumRuntimeSettings:
    base = dict(
        collect_url="https://telemetry.example.test/rum/v1/collect",
        replay_url="https://telemetry.example.test/rum/v1/replay",
        sdk_cdn_url="https://cdn.example.test/rum/bklite-rum-sdk.js",
        nats_url="",
        nats_timeout_seconds=5,
        tenant_id="core",
        victoria_logs_url="",
        victoria_traces_url="",
        victoria_account_id=0,
        victoria_project_id=0,
        victoria_timeout_seconds=15,
    )
    base.update(overrides)
    return RumRuntimeSettings(**base)


def test_apply_degradation_is_exclusive():
    page = apply_degradation({"sessions": []}, REASON_CONTROL)
    assert page["controlUnavailable"] is True
    assert "analyticsUnavailable" not in page
    page = apply_degradation({"controlUnavailable": True, "sessions": []}, REASON_ANALYTICS)
    assert page["analyticsUnavailable"] is True
    assert "controlUnavailable" not in page


def test_empty_helpers_emit_pipeline_flags():
    control = empty_session_list(reason="control")
    assert control["controlUnavailable"] is True
    assert "analyticsUnavailable" not in control
    analytics = empty_release_list(reason="analytics")
    assert analytics["analyticsUnavailable"] is True
    assert "controlUnavailable" not in analytics


def test_resolve_product_scope_control_and_analytics():
    control = MemoryControl()
    ApplicationsService(control, _settings(), analytics=UnavailableAnalytics()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    scoped = resolve_product_scope(
        "tester",
        control=UnavailableControl(),
        analytics=UnavailableAnalytics(),
    )
    assert scoped.reason == REASON_CONTROL
    assert scoped.applications == []

    scoped = resolve_product_scope(
        "tester",
        control=control,
        analytics=UnavailableAnalytics(),
    )
    assert scoped.reason == REASON_ANALYTICS
    assert scoped.applications == ["checkout"]


def test_meta_and_health_report_degraded_flags():
    service = ApplicationsService(
        UnavailableControl(),
        _settings(),
        analytics=UnavailableAnalytics(),
    )
    meta = service.meta()
    assert meta["collectUrl"]
    assert meta["controlUnavailable"] is True
    assert meta["analyticsUnavailable"] is True
    assert meta["controlAvailable"] is False
    assert meta["analyticsAvailable"] is False

    health = service.health("tester")
    assert health["controlUnavailable"] is True
    assert health["analyticsUnavailable"] is True


def test_probe_marks_analytics_configured_from_logs_when_traces_are_empty():
    control = MemoryControl()
    health = probe_pipeline_health(
        control=control,
        analytics=UnavailableAnalytics(),
        settings=_settings(
            nats_url="nats://127.0.0.1:4222",
            victoria_logs_url="http://logs.example.test",
            victoria_traces_url="",
        ),
    )
    assert health.control_configured is True
    assert health.analytics_configured is True
    assert health.control_available is True
    assert health.analytics_available is False
    payload = health.as_dict()
    assert payload["tracesConfigured"] is False
    assert "tracesAvailable" not in payload
    assert "tracesUnavailable" not in payload

    probed = probe_pipeline_health(
        control=control,
        analytics=UnavailableAnalytics(),
        settings=_settings(victoria_logs_url="http://logs.example.test", victoria_traces_url=""),
        probe_traces=True,
    ).as_dict()
    assert probed["tracesConfigured"] is False
    assert probed["tracesAvailable"] is False
    assert probed["tracesUnavailable"] is True


class _ReadyAnalytics:
    def available(self) -> bool:
        return True


def _status_server(status: int) -> tuple[HTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(status)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _recording_server() -> tuple[HTTPServer, str, list[str]]:
    paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            paths.append(self.path)
            self.send_response(200 if self.path.rstrip("/").endswith("/health") else 404)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}", paths


def _pin_victoria(monkeypatch, *, logs: str, traces: str) -> None:
    monkeypatch.setenv("RUM_VICTORIA_LOGS_URL", logs)
    monkeypatch.setenv("RUM_VICTORIA_TRACES_URL", traces)
    monkeypatch.setenv("RUM_VICTORIA_TIMEOUT_SECONDS", "2")


def test_analytics_reads_work_when_logs_are_configured_and_traces_are_empty(monkeypatch):
    server, logs_url, paths = _recording_server()
    _pin_victoria(monkeypatch, logs=logs_url, traces="")
    set_analytics(None)
    try:
        analytics = get_analytics()
        page = analytics.list_sessions("core", {})
        assert analytics.available() is True
        assert page["sessions"] == []
        assert "analyticsUnavailable" not in page
        assert paths == ["/health"]
    finally:
        set_analytics(None)
        server.shutdown()


def test_analytics_stays_unavailable_when_logs_are_empty_even_if_traces_answer(monkeypatch):
    server, traces_url, paths = _recording_server()
    _pin_victoria(monkeypatch, logs="", traces=traces_url)
    set_analytics(None)
    try:
        analytics = get_analytics()
        page = analytics.list_sessions("core", {})
        assert analytics.available() is False
        assert page["analyticsUnavailable"] is True
        assert paths == []
    finally:
        set_analytics(None)
        server.shutdown()


def test_health_reports_traces_up_without_changing_analytics(caplog):
    server, traces_url = _status_server(200)
    try:
        with caplog.at_level(logging.WARNING, logger="rum"):
            service = ApplicationsService(
                MemoryControl(),
                _settings(victoria_logs_url="http://logs.example.test", victoria_traces_url=traces_url),
                analytics=_ReadyAnalytics(),
            )
            health = service.health("tester")
            meta = service.meta()
    finally:
        server.shutdown()
    assert not [record for record in caplog.records if record.msg == "rum traces health unavailable failed_stage=%s error_type=%s"]

    for payload in (health, meta):
        assert payload["analyticsConfigured"] is True
        assert payload["analyticsAvailable"] is True
        assert "analyticsUnavailable" not in payload
        assert payload["tracesConfigured"] is True
        assert "tracesUnavailable" not in payload
    assert health["tracesAvailable"] is True
    assert "tracesAvailable" not in meta


def test_meta_does_not_probe_traces():
    server, traces_url, paths = _recording_server()
    try:
        service = ApplicationsService(
            MemoryControl(),
            _settings(victoria_logs_url="http://logs.example.test", victoria_traces_url=traces_url),
            analytics=_ReadyAnalytics(),
        )
        meta = service.meta()
    finally:
        server.shutdown()
    assert paths == []
    assert meta["tracesConfigured"] is True
    assert "tracesAvailable" not in meta


def test_health_reports_traces_down_while_analytics_stays_available(caplog):
    secret = "rum-traces-sentinel-9f3c"
    server, traces_url = _status_server(503)
    traces_url = f"{traces_url}/{secret}"
    try:
        with caplog.at_level(logging.WARNING, logger="rum"):
            payload = probe_pipeline_health(
                control=MemoryControl(),
                analytics=_ReadyAnalytics(),
                settings=_settings(victoria_logs_url="http://logs.example.test", victoria_traces_url=traces_url),
                probe_traces=True,
            ).as_dict()
    finally:
        server.shutdown()

    assert payload["analyticsConfigured"] is True
    assert payload["analyticsAvailable"] is True
    assert "analyticsUnavailable" not in payload
    assert payload["tracesConfigured"] is True
    assert payload["tracesAvailable"] is False
    assert payload["tracesUnavailable"] is True
    records = [record for record in caplog.records if record.name == "rum"]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.exc_info is None
    assert record.msg == "rum traces health unavailable failed_stage=%s error_type=%s"
    assert record.args == ("traces_health", "HTTPError")
    rendered = record.getMessage()
    assert rendered == "rum traces health unavailable failed_stage=traces_health error_type=HTTPError"
    assert secret not in rendered
    assert secret not in str(record.args)
    assert secret not in caplog.text
    formatted = logging.Formatter().format(record)
    assert secret not in formatted
    assert "Traceback" not in formatted


def test_catalog_marks_configured_false_when_analytics_down():
    control = MemoryControl()
    service = ApplicationsService(control, _settings(), analytics=UnavailableAnalytics())
    service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    catalog = service.analytics_catalog("tester", "24h")
    assert catalog["configured"] is False
    assert catalog["analyticsUnavailable"] is True
    assert catalog["applications"][0]["application"] == "checkout"
