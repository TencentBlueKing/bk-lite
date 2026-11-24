import io
import logging
from urllib.error import HTTPError

import pytest

from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl, UnavailableControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.validation import ValidationError
from apps.rum.services.views import MemorySavedViewStore, ViewsService

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


def test_list_views_degrades_when_analytics_unavailable():
    control = MemoryControl()
    _seed_app(control)
    page = ViewsService(
        control=control,
        analytics=UnavailableAnalytics(),
        saved_views=MemorySavedViewStore(),
    ).list_views("tester", {"range": "24h", "mode": "route"})
    assert page["analyticsUnavailable"] is True
    assert "controlUnavailable" not in page
    assert page["rows"] == []
    assert page["mode"] == "route"


def test_list_views_degrades_when_query_fails(caplog):
    class QueryFailureAnalytics(UnavailableAnalytics):
        def available(self):
            return True

        def list_views(self, tenant_id, opts):
            raise HTTPError(
                "http://127.0.0.1:19428/select/logsql/query",
                400,
                "secret-query-body",
                hdrs=None,
                fp=io.BytesIO(b"secret-query-body"),
            )

    control = MemoryControl()
    _seed_app(control)
    with caplog.at_level(logging.WARNING, logger="rum"):
        page = ViewsService(
            control=control,
            analytics=QueryFailureAnalytics(),
            saved_views=MemorySavedViewStore(),
        ).list_views("tester", {"range": "24h", "mode": "route"})
    assert page["analyticsUnavailable"] is True
    assert "controlUnavailable" not in page
    assert page["rows"] == []
    assert page["mode"] == "route"
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.exc_info is None
    assert record.getMessage() == "rum views list analytics failed failed_stage=list_views error_type=HTTPError"
    assert "secret-query-body" not in record.getMessage()


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


class _RecordingViews:
    def __init__(self, rows=None, *, available=True):
        self.rows = list(rows or [])
        self._available = available
        self.calls = []

    def available(self):
        return self._available

    def list_views(self, tenant_id, opts):
        self.calls.append(opts)
        return {"mode": opts.get("mode") or "route", "summary": {"lcpP75": 0, "inpP75": 0, "clsP75": 0}, "releases": [], "rows": list(self.rows)}


class _ClosedViews(_RecordingViews):
    def __init__(self):
        super().__init__(available=False)

    def list_views(self, tenant_id, opts):
        raise AssertionError("list_views should not run when analytics is unavailable")


def test_list_views_uses_postgres_app_when_control_is_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _RecordingViews(rows=[{"key": "/cart", "route": "/cart"}])
    page = ViewsService(control=UnavailableControl(), analytics=analytics, saved_views=MemorySavedViewStore()).list_views(
        "tester",
        {"range": "24h", "mode": "route"},
    )
    assert analytics.calls[0]["applications"] == ["checkout"]
    assert page["rows"][0]["route"] == "/cart"
    assert page["controlUnavailable"] is True
    assert "analyticsUnavailable" not in page

    empty = _RecordingViews()
    page = ViewsService(control=UnavailableControl(), analytics=empty, saved_views=MemorySavedViewStore()).list_views(
        "tester",
        {"range": "24h"},
    )
    assert empty.calls[0]["applications"] == ["checkout"]
    assert page["rows"] == []
    assert page["controlUnavailable"] is True
    assert "analyticsUnavailable" not in page


def test_list_views_keeps_both_flags_when_control_and_analytics_are_down():
    control = MemoryControl()
    _seed_app(control)
    analytics = _ClosedViews()
    page = ViewsService(control=UnavailableControl(), analytics=analytics, saved_views=MemorySavedViewStore()).list_views(
        "tester",
        {"range": "24h"},
    )
    assert page["controlUnavailable"] is True
    assert page["analyticsUnavailable"] is True
    assert page["rows"] == []
    assert analytics.calls == []


def test_list_views_skips_analytics_when_control_is_down_and_postgres_has_no_app():
    analytics = _RecordingViews(rows=[{"key": "/cart"}])
    page = ViewsService(control=UnavailableControl(), analytics=analytics, saved_views=MemorySavedViewStore()).list_views(
        "tester",
        {"range": "24h"},
    )
    assert page["controlUnavailable"] is True
    assert "analyticsUnavailable" not in page
    assert page["rows"] == []
    assert analytics.calls == []
