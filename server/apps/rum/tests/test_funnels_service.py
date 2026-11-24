import pytest

from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl, UnavailableControl
from apps.rum.services.funnels import FunnelsService, MemoryFunnelStore, normalize_funnel
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


def test_normalize_funnel_requires_path_steps():
    normalized = normalize_funnel({"name": "Checkout", "steps": ["/cart", "/pay"], "application": "checkout"})
    assert normalized["steps"] == ["/cart", "/pay"]
    try:
        normalize_funnel({"name": "Bad", "steps": ["cart", "/pay"]})
        assert False
    except ValidationError:
        pass


def test_funnel_crud_and_reach_degrade():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryFunnelStore()
    service = FunnelsService(control=control, analytics=UnavailableAnalytics(), store=store)

    created = service.create_funnel(
        "tester",
        {"name": "Checkout", "application": "checkout", "steps": ["/cart", "/pay", "/done"]},
    )
    assert created["id"]
    assert len(service.list_funnels()) == 1

    updated = service.update_funnel(
        "tester",
        created["id"],
        {"name": "Checkout v2", "application": "checkout", "steps": ["/cart", "/done"]},
    )
    assert updated["name"] == "Checkout v2"
    assert len(updated["steps"]) == 2

    reach = service.funnel_reach("tester", created["id"], {"range": "24h"})
    assert reach["analyticsUnavailable"] is True
    assert "controlUnavailable" not in reach
    assert reach["steps"] == ["/cart", "/done"]
    assert reach["reached"] == []

    service.delete_funnel(created["id"])
    assert service.list_funnels() == []


def test_funnel_reach_control_unavailable():
    class Boom:
        def available(self):
            return True

        def funnel_reach(self, tenant_id, steps, opts):
            raise AssertionError("analytics queried without a catalog")

    store = MemoryFunnelStore()
    created = store.save({"name": "X", "application": "", "steps": ["/a", "/b"], "defaultPreset": "", "createdBy": "a"})
    reach = FunnelsService(control=UnavailableControl(), analytics=Boom(), store=store).funnel_reach(
        "tester",
        created["id"],
        {"range": "1h"},
    )
    assert reach["controlUnavailable"] is True
    assert "analyticsUnavailable" not in reach
    assert reach["reached"] == []


class _RecordingReach:
    def __init__(self, reached=None, *, available=True):
        self.reached = [2, 1] if reached is None else list(reached)
        self._available = available
        self.calls = []

    def available(self):
        return self._available

    def funnel_reach(self, tenant_id, steps, opts):
        self.calls.append(opts)
        return {"steps": list(steps), "reached": list(self.reached)}


class _ClosedReach(_RecordingReach):
    def __init__(self):
        super().__init__(available=False)

    def funnel_reach(self, tenant_id, steps, opts):
        raise AssertionError("funnel_reach should not run when analytics is unavailable")


def test_funnel_membership_accepts_postgres_app_when_control_is_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _RecordingReach()
    store = MemoryFunnelStore()
    service = FunnelsService(control=UnavailableControl(), analytics=analytics, store=store)
    created = service.create_funnel(
        "tester",
        {"name": "Checkout", "application": "checkout", "steps": ["/cart", "/pay"]},
    )
    updated = service.update_funnel(
        "tester",
        created["id"],
        {"name": "Checkout v2", "application": "checkout", "steps": ["/cart", "/done"]},
    )
    assert updated["name"] == "Checkout v2"
    reach = service.funnel_reach("tester", created["id"], {"range": "24h"})
    assert analytics.calls[0]["applications"] == ["checkout"]
    assert reach["reached"] == [2, 1]
    assert reach["controlUnavailable"] is True
    assert "analyticsUnavailable" not in reach

    empty = _RecordingReach(reached=[])
    empty_service = FunnelsService(control=UnavailableControl(), analytics=empty, store=store)
    empty_reach = empty_service.funnel_reach("tester", created["id"], {"range": "24h"})
    assert empty.calls[0]["applications"] == ["checkout"]
    assert empty_reach["reached"] == []
    assert empty_reach["controlUnavailable"] is True
    assert "analyticsUnavailable" not in empty_reach

    try:
        service.create_funnel(
            "tester",
            {"name": "Missing", "application": "other", "steps": ["/cart", "/pay"]},
        )
        assert False, "expected not_found"
    except ControlError as exc:
        assert exc.code == "not_found"


def test_funnel_reach_keeps_both_flags_when_control_and_analytics_are_down():
    control = MemoryControl()
    _seed_app(control)
    store = MemoryFunnelStore()
    created = store.save({"name": "Checkout", "application": "checkout", "steps": ["/cart", "/pay"], "defaultPreset": "", "createdBy": "tester"})
    analytics = _ClosedReach()
    reach = FunnelsService(control=UnavailableControl(), analytics=analytics, store=store).funnel_reach(
        "tester",
        created["id"],
        {"range": "24h"},
    )
    assert reach["controlUnavailable"] is True
    assert reach["analyticsUnavailable"] is True
    assert reach["reached"] == []
    assert reach["steps"] == ["/cart", "/pay"]
    assert analytics.calls == []


def test_funnel_create_still_reports_control_when_postgres_has_no_app():
    service = FunnelsService(control=UnavailableControl(), store=MemoryFunnelStore())
    try:
        service.create_funnel(
            "tester",
            {"name": "Checkout", "application": "checkout", "steps": ["/cart", "/pay"]},
        )
        assert False, "expected unavailable"
    except ControlError as exc:
        assert exc.code == "unavailable"
