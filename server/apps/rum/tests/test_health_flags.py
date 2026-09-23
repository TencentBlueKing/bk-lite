from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.health import REASON_ANALYTICS, REASON_CONTROL, probe_pipeline_health, resolve_product_scope
from apps.rum.services.query import apply_degradation, empty_release_list, empty_session_list
from apps.rum.services.settings import RumRuntimeSettings


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


def test_probe_marks_configured_when_endpoints_present():
    control = MemoryControl()
    health = probe_pipeline_health(
        control=control,
        analytics=UnavailableAnalytics(),
        settings=_settings(
            nats_url="nats://127.0.0.1:4222",
            victoria_logs_url="http://127.0.0.1:9428",
            victoria_traces_url="http://127.0.0.1:9429",
        ),
    )
    assert health.control_configured is True
    assert health.analytics_configured is True
    assert health.control_available is True
    assert health.analytics_available is False


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
