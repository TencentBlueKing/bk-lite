from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl, UnavailableControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError
from apps.rum.services.views import MemorySavedViewStore, ViewsService


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


def test_list_views_degrades_when_analytics_unavailable():
    control = MemoryControl()
    _seed_app(control)
    page = ViewsService(
        control=control,
        analytics=UnavailableAnalytics(),
        saved_views=MemorySavedViewStore(),
    ).list_views("tester", {"range": "24h", "mode": "route"})
    assert page["analyticsUnavailable"] is True
    assert page["rows"] == []
    assert page["mode"] == "route"


def test_list_views_degrades_when_control_unavailable():
    page = ViewsService(control=UnavailableControl(), saved_views=MemorySavedViewStore()).list_views("tester", {"range": "24h"})
    assert page["controlUnavailable"] is True


def test_list_views_rejects_bad_mode():
    try:
        ViewsService(control=MemoryControl(), saved_views=MemorySavedViewStore()).list_views("tester", {"mode": "weird"})
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_saved_views_crud_for_owner():
    store = MemorySavedViewStore()
    service = ViewsService(control=MemoryControl(), saved_views=store)
    created = service.create_saved_view(
        "tester",
        {
            "screen": "sessions",
            "name": "Errored only",
            "contextJson": '{"hasError":true}',
            "shared": False,
        },
    )
    assert created["id"]
    assert created["owner"] == "tester"
    assert created["contextJson"] == '{"hasError":true}'
    assert len(service.list_saved_views("tester", "sessions")) == 1
    service.delete_saved_view("tester", created["id"])
    assert service.list_saved_views("tester", "sessions") == []


def test_shared_saved_view_visible_to_others_but_not_deletable():
    store = MemorySavedViewStore()
    service = ViewsService(control=MemoryControl(), saved_views=store)
    created = service.create_saved_view(
        "alice",
        {"screen": "views", "name": "Shared CWV", "contextJson": "{}", "shared": True},
    )
    assert len(service.list_saved_views("bob", "views")) == 1
    try:
        service.delete_saved_view("bob", created["id"])
        assert False, "expected forbidden"
    except ControlError as exc:
        assert exc.code == "forbidden"
