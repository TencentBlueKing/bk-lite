from apps.rum.services.analytics import UnavailableAnalytics
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.errors import MemorySourcemapStore
from apps.rum.services.releases import MemoryBaselineStore, MemoryCredentialStore, ReleasesService
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.sourcemap import asset_fingerprint
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


def _service(control=None, **kwargs) -> ReleasesService:
    return ReleasesService(
        control=control or MemoryControl(),
        analytics=kwargs.get("analytics"),
        baselines=kwargs.get("baselines") or MemoryBaselineStore(),
        sourcemaps=kwargs.get("sourcemaps") or MemorySourcemapStore(),
        credentials=kwargs.get("credentials") or MemoryCredentialStore(),
    )


def test_asset_fingerprint_matches_wire_contract():
    expected = "asset:9ab0ce4d26f7d0ad959edd4b45878c1b"
    assert asset_fingerprint("https://cdn.example.test/assets/checkout.min.js?v=7#x") == expected
    assert asset_fingerprint("/assets/checkout.min.js") == expected
    assert asset_fingerprint("../main.js") == ""
    assert asset_fingerprint("javascript:alert(1)") == ""


def test_list_releases_degrades_without_analytics():
    control = MemoryControl()
    _seed_app(control)
    page = _service(control, analytics=UnavailableAnalytics()).list_releases("tester", {"range": "24h", "application": "checkout"})
    assert page["releases"] == []
    assert page["analyticsUnavailable"] is True


def test_list_releases_degrades_without_control():
    page = _service(UnavailableControl()).list_releases("tester", {"range": "24h"})
    assert page["releases"] == []
    assert page["controlUnavailable"] is True


def test_baseline_upsert_marks_release():
    control = MemoryControl()
    _seed_app(control)
    baselines = MemoryBaselineStore()
    service = _service(control, baselines=baselines)
    item = service.put_baseline("tester", "checkout", {"baselineRelease": "1.2.0"})
    assert item["application"] == "checkout"
    assert item["baselineRelease"] == "1.2.0"
    assert baselines.list()[0]["baselineRelease"] == "1.2.0"


def test_sourcemap_upload_and_list():
    control = MemoryControl()
    _seed_app(control)
    maps = MemorySourcemapStore()
    service = _service(control, sourcemaps=maps)
    content = b'{"version":3,"file":"out.js","sources":["src/a.ts"],"names":[],"mappings":"AAAA"}'
    saved = service.upload_sourcemap(
        "tester",
        {
            "application": "checkout",
            "release": "1.0.0",
            "asset": "/assets/checkout.min.js",
        },
        content,
    )
    assert saved["fileName"] == "asset:9ab0ce4d26f7d0ad959edd4b45878c1b"
    assert "content" not in saved
    listed = service.list_sourcemaps("tester", {"application": "checkout"})
    assert len(listed) == 1
    assert listed[0]["id"] == saved["id"]
    # No registry-wide listing without an application.
    try:
        service.list_sourcemaps("tester", {})
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_sourcemap_upload_rejects_invalid_map():
    control = MemoryControl()
    _seed_app(control)
    try:
        _service(control).upload_sourcemap(
            "tester",
            {
                "application": "checkout",
                "release": "1.0.0",
                "asset": "/assets/checkout.min.js",
            },
            b"not-a-map",
        )
        assert False
    except ValidationError:
        pass


def test_credential_rotate_and_ci_ingest():
    control = MemoryControl()
    _seed_app(control)
    credentials = MemoryCredentialStore()
    maps = MemorySourcemapStore()
    service = _service(control, sourcemaps=maps, credentials=credentials)
    rotated = service.rotate_credential("tester", "checkout")
    assert rotated["token"].startswith("rumsm_")
    content = b'{"version":3,"file":"out.js","sources":["src/a.ts"],"names":[],"mappings":"AAAA"}'
    ingested = service.ingest_sourcemap(
        f"Bearer {rotated['token']}",
        {
            "application": "checkout",
            "release": "1.0.0",
            "asset": "https://cdn.example.test/assets/checkout.min.js",
        },
        content,
    )
    assert ingested["createdBy"] == "ci:checkout"
    assert maps.find("checkout", "1.0.0", ingested["fileName"]) is not None


def test_ci_ingest_rejects_bad_token():
    control = MemoryControl()
    _seed_app(control)
    service = _service(control)
    service.rotate_credential("tester", "checkout")
    try:
        service.ingest_sourcemap(
            "Bearer wrong-token",
            {
                "application": "checkout",
                "release": "1.0.0",
                "asset": "/assets/checkout.min.js",
            },
            b'{"version":3,"mappings":""}',
        )
        assert False
    except Exception as exc:
        assert getattr(exc, "code", "") == "forbidden"
