import pytest
from django.test import override_settings

from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl, UnavailableControl
from apps.rum.services.query import parse_range_params
from apps.rum.services.replay import MemoryReplayIndex
from apps.rum.services.sessions import SessionsService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError

pytestmark = pytest.mark.django_db


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
    assert "controlUnavailable" not in listed
    assert listed["sessions"] == []
    trend = service.session_trend("tester", {"range": "24h"})
    assert trend["analyticsUnavailable"] is True
    assert "controlUnavailable" not in trend
    assert trend["points"] == []


def test_list_and_trend_degrade_when_analytics_raises():
    class BoomAnalytics:
        def available(self):
            return True

        def list_sessions(self, tenant_id, opts):
            raise RuntimeError("victoria blew up")

        def session_trend(self, tenant_id, opts):
            raise RuntimeError("victoria blew up")

    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=control, analytics=BoomAnalytics())
    listed = service.list_sessions("tester", {"range": "24h"})
    assert listed["analyticsUnavailable"] is True
    assert "controlUnavailable" not in listed
    assert listed["sessions"] == []
    trend = service.session_trend("tester", {"range": "24h"})
    assert trend["analyticsUnavailable"] is True
    assert "controlUnavailable" not in trend
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
    from apps.rum.services.replay import UnavailableReplayIndex

    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=control, replay_index=UnavailableReplayIndex())
    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["analyticsUnavailable"] is True
    assert "controlUnavailable" not in manifest
    assert manifest["state"] == "unavailable"


class _RecordingAnalytics:
    def __init__(self, sessions=None, *, available=True, trend_points=None):
        self.sessions = list(sessions or [])
        self.trend_points = list(trend_points or [])
        self._available = available
        self.calls = []

    def available(self):
        return self._available

    def list_sessions(self, tenant_id, opts):
        self.calls.append(("list", opts))
        return {
            "sessions": list(self.sessions),
            "summary": {"total": len(self.sessions), "errored": 0, "replayed": 0, "medianDurationMs": 0},
        }

    def session_trend(self, tenant_id, opts):
        self.calls.append(("trend", opts))
        return {"points": list(self.trend_points)}

    def session_journey(self, tenant_id, application, session_id, opts):
        self.calls.append(("journey", application, session_id))
        return {
            "session": {"sessionId": session_id, "application": application},
            "views": [],
            "actions": [],
            "errors": [],
            "vitals": [],
            "network": [],
            "console": [],
        }


class _ClosedAnalytics(_RecordingAnalytics):
    def __init__(self):
        super().__init__(available=False)

    def list_sessions(self, tenant_id, opts):
        raise AssertionError("list_sessions should not run when analytics is unavailable")

    def session_trend(self, tenant_id, opts):
        raise AssertionError("session_trend should not run when analytics is unavailable")

    def session_journey(self, tenant_id, application, session_id, opts):
        raise AssertionError("session_journey should not run when analytics is unavailable")


def test_list_and_trend_use_postgres_app_when_control_is_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _RecordingAnalytics(
        sessions=[{"application": "checkout", "sessionId": "s1", "errorCount": 0}],
        trend_points=[{"bucket": "2026-01-01T00:00:00Z", "sessions": 1}],
    )
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    listed = service.list_sessions("tester", {"range": "24h"})
    trend = service.session_trend("tester", {"range": "24h"})
    assert analytics.calls[0][0] == "list"
    assert analytics.calls[0][1]["applications"] == ["checkout"]
    assert analytics.calls[1] == ("trend", analytics.calls[1][1])
    assert analytics.calls[1][1]["applications"] == ["checkout"]
    assert listed["sessions"][0]["sessionId"] == "s1"
    assert listed["controlUnavailable"] is True
    assert "analyticsUnavailable" not in listed
    assert trend["points"]
    assert trend["controlUnavailable"] is True
    assert "analyticsUnavailable" not in trend

    empty = _RecordingAnalytics()
    empty_service = SessionsService(control=UnavailableControl(), analytics=empty)
    listed = empty_service.list_sessions("tester", {"range": "24h"})
    assert empty.calls[0][1]["applications"] == ["checkout"]
    assert listed["sessions"] == []
    assert listed["controlUnavailable"] is True
    assert "analyticsUnavailable" not in listed


def test_list_and_trend_keep_both_flags_when_control_and_analytics_are_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _ClosedAnalytics()
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    listed = service.list_sessions("tester", {"range": "24h"})
    trend = service.session_trend("tester", {"range": "24h"})
    assert listed["controlUnavailable"] is True
    assert listed["analyticsUnavailable"] is True
    assert listed["sessions"] == []
    assert trend["controlUnavailable"] is True
    assert trend["analyticsUnavailable"] is True
    assert trend["points"] == []
    assert analytics.calls == []
    journey = service.get_session("tester", "sess-1", {"application": "checkout", "range": "24h"})
    assert journey["controlUnavailable"] is True
    assert journey["analyticsUnavailable"] is True
    assert journey["session"] == {}
    assert analytics.calls == []


def test_list_skips_analytics_when_control_is_down_and_postgres_has_no_app():
    analytics = _RecordingAnalytics(sessions=[{"application": "checkout", "sessionId": "s1", "errorCount": 0}])
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    listed = service.list_sessions("tester", {"range": "24h"})
    trend = service.session_trend("tester", {"range": "24h"})
    assert listed["controlUnavailable"] is True
    assert "analyticsUnavailable" not in listed
    assert listed["sessions"] == []
    assert trend["controlUnavailable"] is True
    assert "analyticsUnavailable" not in trend
    assert trend["points"] == []
    journey = service.get_session("tester", "sess-1", {"application": "checkout", "range": "24h"})
    assert journey["controlUnavailable"] is True
    assert "analyticsUnavailable" not in journey
    assert journey["session"] == {}
    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["controlUnavailable"] is True
    assert "analyticsUnavailable" not in manifest
    assert manifest["state"] == "unavailable"
    assert analytics.calls == []


def test_disabled_postgres_app_stays_out_of_the_fallback_catalog():
    control = MemoryControl()
    _seed_app(control)
    ApplicationsService(control, _settings()).create_application(
        "tester",
        {"application": "storefront", "origins": ["https://shop.example.test"]},
    )
    ApplicationsService(control, _settings()).disable_application("tester", "checkout")
    analytics = _RecordingAnalytics()
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    service.list_sessions("tester", {"range": "24h"})
    assert analytics.calls[0][1]["applications"] == ["storefront"]


def test_controller_registry_wins_when_the_list_succeeds():
    control = MemoryControl()
    _seed_app(control)

    class EmptyRegistry:
        def available(self):
            return True

        def request(self, subject, actor, payload=None, expected_revision=None):
            return 0, []

    analytics = _RecordingAnalytics()
    service = SessionsService(control=EmptyRegistry(), analytics=analytics)
    listed = service.list_sessions("tester", {"range": "24h"})
    assert analytics.calls[0][1]["applications"] == []
    assert "controlUnavailable" not in listed
    assert "analyticsUnavailable" not in listed


def test_journey_and_replay_use_postgres_app_when_control_is_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _RecordingAnalytics()
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    journey = service.get_session("tester", "sess-1", {"application": "checkout", "range": "24h"})
    assert analytics.calls == [("journey", "checkout", "sess-1")]
    assert journey["session"]["sessionId"] == "sess-1"
    assert journey["controlUnavailable"] is True
    assert "analyticsUnavailable" not in journey
    try:
        service.get_session("tester", "sess-1", {"application": "other", "range": "24h"})
        assert False, "expected not_found"
    except ControlError as exc:
        assert exc.code == "not_found"


@override_settings(RUM_REPLAY_SIGNING_SECRET="dev-bklite-rum-replay-signing-secret-32b")
def test_replay_grant_still_checks_signature_when_control_is_down():
    control = MemoryControl()
    _seed_app(control)
    index = MemoryReplayIndex()
    index.mark_ready("checkout", "sess-1")
    service = SessionsService(control=UnavailableControl(), replay_index=index)
    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["state"] == "ready"
    assert manifest["controlUnavailable"] is True
    assert "analyticsUnavailable" not in manifest
    ref = manifest["recordings"][0]["segments"][0]["ref"]
    try:
        service.replay_grant("tester", {"application": "checkout", "session": "sess-1", "targetRef": "not-a-ref"})
        assert False, "expected ValidationError"
    except ValidationError:
        pass
    grant = service.replay_grant("tester", {"application": "checkout", "session": "sess-1", "targetRef": ref})
    assert grant["targetIncluded"] is True
    assert "controlUnavailable" not in grant


def test_query_failure_keeps_control_flag_when_postgres_app_exists():
    class Boom(_RecordingAnalytics):
        def list_sessions(self, tenant_id, opts):
            self.calls.append(("list", opts))
            raise RuntimeError("victoria")

        def session_trend(self, tenant_id, opts):
            self.calls.append(("trend", opts))
            raise RuntimeError("victoria")

    control = MemoryControl()
    _seed_app(control)
    analytics = Boom()
    service = SessionsService(control=UnavailableControl(), analytics=analytics)
    listed = service.list_sessions("tester", {"range": "24h"})
    trend = service.session_trend("tester", {"range": "24h"})
    assert analytics.calls[0][1]["applications"] == ["checkout"]
    assert analytics.calls[1][1]["applications"] == ["checkout"]
    assert listed["controlUnavailable"] is True
    assert listed["analyticsUnavailable"] is True
    assert trend["controlUnavailable"] is True
    assert trend["analyticsUnavailable"] is True


def test_replay_manifest_keeps_both_flags_when_control_and_index_are_down():
    from apps.rum.services.replay import UnavailableReplayIndex

    control = MemoryControl()
    _seed_app(control)
    service = SessionsService(control=UnavailableControl(), replay_index=UnavailableReplayIndex())
    manifest = service.replay_manifest("tester", {"application": "checkout", "session": "sess-1"})
    assert manifest["controlUnavailable"] is True
    assert manifest["analyticsUnavailable"] is True
    assert manifest["state"] == "unavailable"
    assert manifest["recordings"] == []
