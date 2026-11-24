from datetime import timedelta

import pytest
from django.utils import timezone

from apps.rum.constants import DEFAULT_BUDGETS, SUBJECT_APPLICATION_GET
from apps.rum.models import RumApplication
from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import ControlError, MemoryControl, UnavailableControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.snippets import build_snippet
from apps.rum.services.status import build_status
from apps.rum.services.validation import ValidationError, canonical_origins, valid_application

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


def test_list_applications_orders_by_created_at_desc():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application("tester", {"application": "alpha", "origins": ["https://alpha.example.test"]})
    service.create_application("tester", {"application": "zeta", "origins": ["https://zeta.example.test"]})
    RumApplication.objects.filter(name="alpha").update(created_at=timezone.now() - timedelta(days=1))

    listed = service.list_applications("tester")

    assert [item["application"] for item in listed] == ["zeta", "alpha"]


def test_valid_application_and_origins():
    assert valid_application("checkout")
    assert not valid_application("")
    assert canonical_origins(["https://Example.COM"]) == ["https://example.com"]


def test_create_list_get_disable_flow():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    revision, created = service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    assert revision == 1
    assert created["application"] == "checkout"
    assert created["enabled"] is True
    assert created["orgId"] == "core"
    assert created["browserKeys"]
    assert created["budgets"]["requestsPerMinute"] == DEFAULT_BUDGETS["requestsPerMinute"]

    listed = service.list_applications("tester")
    assert len(listed) == 1
    # Registry overview never carries plaintext keys; only per-app get does.
    assert "browserKeys" not in listed[0]
    assert listed[0]["application"] == "checkout"

    got = service.get_application("tester", "checkout")
    assert got["revision"] == 1
    assert got["browserKeys"] == created["browserKeys"]


def test_create_ignores_client_supplied_org_id():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    _, created = service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"], "orgId": "someone-else"},
    )
    assert created["orgId"] == "core"

    _, disabled = service.disable_application("tester", "checkout")
    assert disabled["enabled"] is False

    status_payload = service.status("tester", "checkout")
    assert status_payload["status"] == "disabled"


def test_status_degrades_when_controller_unavailable():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application("tester", {"application": "checkout", "origins": ["https://shop.example.test"]})
    service.control = UnavailableControl()
    payload = service.status("tester", "checkout")
    assert payload["controllerUnreachable"] is True
    assert payload["status"] == "waiting"


def test_list_applications_degrades_to_empty_when_controller_unavailable():
    service = ApplicationsService(UnavailableControl(), _settings())
    assert service.list_applications("tester") == []


def test_analytics_catalog_marks_control_unavailable():
    service = ApplicationsService(UnavailableControl(), _settings(), analytics=UnavailableAnalytics())
    catalog = service.analytics_catalog("tester", "24h")
    assert catalog["applications"] == []
    assert catalog["controlUnavailable"] is True
    assert catalog["configured"] is False


def test_analytics_and_overview_mark_analytics_unavailable():
    control = MemoryControl()
    service = ApplicationsService(control, _settings(), analytics=UnavailableAnalytics())
    service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    catalog = service.analytics_catalog("tester", "24h")
    assert catalog["analyticsUnavailable"] is True
    assert catalog["applications"][0]["application"] == "checkout"

    overview = service.overview("tester", "checkout", "1h")
    assert overview["analyticsUnavailable"] is True
    assert overview["range"] == "1h"


def _snippet_body(**extra):
    body = {
        "application": "checkout",
        "browserKey": "browser-key-abcdefgh",
        "collectUrl": "https://telemetry.example.test/rum/v1/collect",
        "replayUrl": "https://telemetry.example.test/rum/v1/replay",
        "sdkCdnUrl": "https://cdn.example.test/rum/bklite-rum-sdk.js",
        "replay": {"enabled": False},
    }
    body.update(extra)
    return body


_SDK_CDN = "https://cdn.example.test/rum/bklite-rum-sdk.js"


def test_snippets_use_bklite_rum_sdk():
    set_ = build_snippet(_snippet_body(), _SDK_CDN)
    npm = set_["npm"]
    advanced = set_["advanced"]["npm"]
    assert "from 'bklite-rum-sdk'" in npm
    assert "bklite-rum-sdk@0.1.0" not in npm
    assert "bklite-rum-sdk@0.1.0" in advanced
    assert "initCoreRum" in set_["cdn"]
    assert "bklite-rum-sdk.js" in set_["cdn"]
    assert "logicalViewNameForPathname" not in npm
    assert "bun add --exact" not in npm
    assert "package.json overrides" not in npm
    assert "logicalViewNameForPathname" in advanced
    assert "pushState" in advanced
    assert "package.json overrides" in advanced
    assert "apiKey: 'browser-key-abcdefgh'" in npm
    assert "collectUrl: 'https://telemetry.example.test/rum/v1/collect'" in npm
    assert "FaroRouteView" not in set_["react"]
    assert "logicalViewNameForPathname" not in set_["react"]
    assert "FaroRouteView" in set_["advanced"]["react"]
    assert "logicalViewNameForPathname" in set_["advanced"]["react"]


def test_snippet_session_sampling_rate():
    omitted = build_snippet(_snippet_body(), _SDK_CDN)
    sampled = build_snippet(_snippet_body(sessionSamplingRate=0.2), _SDK_CDN)
    explicit_one = build_snippet(_snippet_body(sessionSamplingRate=1), _SDK_CDN)
    zero = build_snippet(_snippet_body(sessionSamplingRate=0), _SDK_CDN)
    for key in ("npm", "react", "generic", "cdn"):
        assert "sessionTracking: { enabled: true, samplingRate: 1 }" in omitted[key]
        assert "sessionTracking: { enabled: true, samplingRate: 0.2 }" in sampled[key]
        assert "samplingRate: 0.2" not in sampled["advanced"][key]
        assert "sessionTracking: { enabled: true, samplingRate: 1 }" in explicit_one[key]
        assert "samplingRate: 1.0" not in explicit_one[key]
        assert "sessionTracking: { enabled: true, samplingRate: 0 }" in zero[key]
    assert "replay: { enabled: false }" in sampled["npm"]
    with pytest.raises(ValidationError, match="sessionSamplingRate must be between 0 and 1"):
        build_snippet(_snippet_body(sessionSamplingRate=2), _SDK_CDN)


def test_update_application_preserves_ingest_evidence():
    control = MemoryControl()
    service = ApplicationsService(control, _settings())
    service.create_application(
        "tester",
        {"application": "checkout", "origins": ["https://shop.example.test"]},
    )
    control._apps["checkout"]["lastAcceptedAt"] = 1_700_000_000
    control._apps["checkout"]["lastStoredAt"] = 1_700_000_010
    _, updated = service.update_application(
        "tester",
        "checkout",
        {"origins": ["https://shop.example.test"]},
    )
    assert updated["lastAcceptedAt"] == 1_700_000_000
    assert updated["lastStoredAt"] == 1_700_000_010


def test_build_status_connected_when_evidence_fresh():
    now = 1_700_000_000
    payload = build_status(
        {
            "application": "checkout",
            "enabled": True,
            "lastAcceptedAt": now - 60,
            "lastStoredAt": now - 30,
        },
        application="checkout",
        now=now,
    )
    assert payload["status"] == "connected"


def test_build_status_connected_at_fifteen_minute_boundary():
    now = 1_700_000_000
    payload = build_status(
        {
            "application": "checkout",
            "enabled": True,
            "lastAcceptedAt": now - 15 * 60,
            "lastStoredAt": now - 15 * 60,
        },
        application="checkout",
        now=now,
    )
    assert payload["status"] == "connected"


def test_build_status_waiting_when_evidence_older_than_window():
    now = 1_700_000_000
    payload = build_status(
        {
            "application": "checkout",
            "enabled": True,
            "lastAcceptedAt": now - 15 * 60 - 1,
            "lastStoredAt": now - 30,
        },
        application="checkout",
        now=now,
    )
    assert payload["status"] == "waiting"


class _FailingGet(MemoryControl):
    def __init__(self):
        super().__init__()
        self.gets = 0

    def request(self, subject, actor, payload=None, expected_revision=None):
        if subject == SUBJECT_APPLICATION_GET:
            self.gets += 1
            raise ControlError("unavailable", "down")
        return super().request(subject, actor, payload, expected_revision)


def test_catalog_and_brief_list_do_not_call_nats():
    class _Counting(MemoryControl):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def request(self, subject, actor, payload=None, expected_revision=None):
            self.calls += 1
            return super().request(subject, actor, payload, expected_revision)

    class _Analytics:
        def __init__(self):
            self.apps = None

        def available(self):
            return True

        def applications_page(self, tenant_id, start, end, enabled_apps):
            self.apps = list(enabled_apps)
            return (
                [
                    {
                        "application": "zeta",
                        "sessions": 2,
                        "views": 3,
                        "errors": 1,
                        "lcpP75": 10,
                        "inpP75": 4,
                        "errorRate": 0.5,
                    }
                ],
                {"zeta": [1.0]},
            )

    writer = ApplicationsService(MemoryControl(), _settings())
    writer.create_application("tester", {"application": "alpha", "origins": ["https://alpha.example.test"]})
    writer.create_application("tester", {"application": "zeta", "origins": ["https://zeta.example.test"]})
    writer.disable_application("tester", "alpha")
    control = _Counting()
    analytics = _Analytics()
    service = ApplicationsService(control, _settings(), analytics=analytics)

    catalog = service.analytics_catalog("tester", "24h")
    names = service.list_application_names("tester")

    assert control.calls == 0
    assert analytics.apps == ["zeta"]
    assert [item["application"] for item in catalog["applications"]] == ["zeta", "alpha"]
    assert catalog["applications"][0]["sessions"] == 2
    assert catalog["applications"][1]["enabled"] is False
    assert names == [
        {"application": "zeta", "enabled": True},
        {"application": "alpha", "enabled": False},
    ]


def test_full_list_stops_nats_after_the_first_control_failure():
    writer = ApplicationsService(MemoryControl(), _settings())
    writer.create_application("tester", {"application": "alpha", "origins": ["https://alpha.example.test"]})
    writer.create_application("tester", {"application": "zeta", "origins": ["https://zeta.example.test"]})
    control = _FailingGet()
    service = ApplicationsService(control, _settings())

    listed = service.list_applications("tester")

    assert control.gets == 1
    assert [item["application"] for item in listed] == ["zeta", "alpha"]
    assert all(item["controlUnavailable"] is True for item in listed)


def test_invalid_origins_raise():
    try:
        canonical_origins(["https://example.com/path"])
        assert False, "expected ValidationError"
    except ValidationError:
        pass
