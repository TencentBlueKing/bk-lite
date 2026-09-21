from apps.rum.constants import DEFAULT_BUDGETS
from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.snippets import build_snippet
from apps.rum.services.status import build_status
from apps.rum.services.validation import ValidationError, canonical_origins, valid_application


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
    service = ApplicationsService(UnavailableControl(), _settings())
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


def test_snippets_use_bklite_rum_sdk():
    set_ = build_snippet(
        {
            "application": "checkout",
            "browserKey": "browser-key-abcdefgh",
            "collectUrl": "https://telemetry.example.test/rum/v1/collect",
            "replayUrl": "https://telemetry.example.test/rum/v1/replay",
            "sdkCdnUrl": "https://cdn.example.test/rum/bklite-rum-sdk.js",
            "replay": {"enabled": False},
        },
        "https://cdn.example.test/rum/bklite-rum-sdk.js",
    )
    assert "bklite-rum-sdk@0.1.0" in set_["npm"]
    assert "from 'bklite-rum-sdk'" in set_["npm"]
    assert "initCoreRum" in set_["cdn"]
    assert "bklite-rum-sdk.js" in set_["cdn"]
    npm = set_["npm"]
    assert npm.index("apiKey: 'browser-key-abcdefgh'") < npm.index("logicalViewNameForPathname")
    assert npm.index("collectUrl: 'https://telemetry.example.test/rum/v1/collect'") < npm.index("logicalViewNameForPathname")


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


def test_invalid_origins_raise():
    try:
        canonical_origins(["https://example.com/path"])
        assert False, "expected ValidationError"
    except ValidationError:
        pass
