from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.funnels import FunnelsService, MemoryFunnelStore, normalize_funnel
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
    assert reach["steps"] == ["/cart", "/done"]
    assert reach["reached"] == []

    service.delete_funnel(created["id"])
    assert service.list_funnels() == []


def test_funnel_reach_control_unavailable():
    store = MemoryFunnelStore()
    created = store.save({"name": "X", "application": "", "steps": ["/a", "/b"], "defaultPreset": "", "createdBy": "a"})
    reach = FunnelsService(control=UnavailableControl(), store=store).funnel_reach("tester", created["id"], {"range": "1h"})
    assert reach["controlUnavailable"] is True
