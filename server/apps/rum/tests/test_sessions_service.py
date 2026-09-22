import pytest
from django.test import override_settings

from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.query import parse_range_params
from apps.rum.services.replay import MemoryReplayIndex
from apps.rum.services.sessions import SessionsService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError


def _settings() -> RumRuntimeSettings:
    return RumRuntimeSettings(
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


def _seed_app(control: MemoryControl) -> None:
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )


def test_parse_range_accepts_named_windows():
    start, end = parse_range_params({"range": "1h"})
    assert (end - start).total_seconds() == pytest.approx(3600, abs=2)


def test_list_and_trend_degrade_when_analytics_unavailable():
    from apps.rum.services.analytics import UnavailableAnalytics

    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=control, analytics=UnavailableAnalytics())
    listed = service.list_sessions("tester", {"range": "24h"})
    assert listed["analyticsUnavailable"] is True
    assert listed["sessions"] == []
    trend = service.session_trend("tester", {"range": "24h"})
    assert trend["analyticsUnavailable"] is True
    assert trend["points"] == []


def test_list_degrades_when_control_unavailable():
    service = SessionsService(control=UnavailableControl())
    listed = service.list_sessions("tester", {"range": "24h"})
    assert listed["controlUnavailable"] is True


def test_detail_requires_application():
    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=control)
    try:
        service.get_session("tester", "sess-1", {"range": "24h"})
        assert False, "expected ValidationError"
    except ValidationError:
        pass


@override_settings(RUM_REPLAY_SIGNING_SECRET="dev-bklite-rum-replay-signing-secret-32b")
def test_replay_manifest_grant_and_segment_contract():
    control = MemoryControl()
    _seed_app(control)
    index = MemoryReplayIndex()
    index.mark_ready("checkout", "sess-1")
    service = SessionsService(control=control, replay_index=index)

    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["state"] == "ready"
    ref = manifest["recordings"][0]["segments"][0]["ref"]
    assert ref
    assert "objectKey" not in manifest["recordings"][0]["segments"][0]

    grant = service.replay_grant(
        "tester",
        {"application": "checkout", "session": "sess-1", "targetRef": ref},
    )
    assert grant["targetIncluded"] is True
    assert grant["segments"][0]["url"].startswith("/api/v1/rum/replay/segments/")

    token = grant["segments"][0]["url"].rsplit("/", 1)[-1]
    claims = service.replay_segment_claims(token)
    assert claims["objectKey"].endswith("0.rrweb")


def test_replay_manifest_degrades_without_index():
    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=control)
    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["analyticsUnavailable"] is True
    assert manifest["state"] == "unavailable"
