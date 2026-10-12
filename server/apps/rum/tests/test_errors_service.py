import io
import logging
from urllib.error import HTTPError

import pytest

from apps.rum.services.analytics import UnavailableAnalytics

pytestmark = pytest.mark.django_db
from apps.rum.services.applications import ApplicationsService
from apps.rum.services.control import MemoryControl, UnavailableControl
from apps.rum.services.errors import ErrorsService, MemoryIssueStore, MemorySourcemapStore, match_issue_status
from apps.rum.services.settings import RumRuntimeSettings
from apps.rum.services.sourcemap import OUTCOME_MISSING_RELEASE, OUTCOME_RESOLVED, restore_frames


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


def test_match_issue_status_filters():
    assert match_issue_status("open", "active")
    assert not match_issue_status("resolved", "active")
    assert match_issue_status("ignored", "ignored")


def test_list_errors_degrades_without_analytics():
    control = MemoryControl()
    _seed_app(control)
    page = ErrorsService(
        control=control,
        analytics=UnavailableAnalytics(),
        issues=MemoryIssueStore(),
    ).list_errors("tester", {"range": "24h"})
    assert page["analyticsUnavailable"] is True
    assert page["issues"] == []


def _query_failure():
    class QueryFailureAnalytics(UnavailableAnalytics):
        def available(self):
            return True

        def list_error_issues(self, tenant_id, opts):
            raise _http_error()

        def error_detail(self, tenant_id, fingerprint, opts):
            raise _http_error()

    return QueryFailureAnalytics()


def _http_error() -> HTTPError:
    return HTTPError(
        "http://127.0.0.1:19428/select/logsql/query",
        400,
        "secret-query-body",
        hdrs=None,
        fp=io.BytesIO(b"secret-query-body"),
    )


def test_list_errors_degrades_when_query_fails(caplog):
    control = MemoryControl()
    _seed_app(control)
    with caplog.at_level(logging.WARNING, logger="rum"):
        page = ErrorsService(
            control=control,
            analytics=_query_failure(),
            issues=MemoryIssueStore(),
        ).list_errors("tester", {"range": "24h"})
    assert page["analyticsUnavailable"] is True
    assert page["issues"] == []
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.exc_info is None
    assert record.getMessage() == "rum errors list analytics failed failed_stage=list_errors error_type=HTTPError"
    assert "secret-query-body" not in record.getMessage()


def test_error_detail_degrades_when_query_fails(caplog):
    control = MemoryControl()
    _seed_app(control)
    with caplog.at_level(logging.WARNING, logger="rum"):
        page = ErrorsService(
            control=control,
            analytics=_query_failure(),
            issues=MemoryIssueStore(),
        ).error_detail("tester", "fp-1", {"range": "24h"})
    assert page["analyticsUnavailable"] is True
    assert page["fingerprint"] == ""
    record = next(item for item in caplog.records if item.name == "rum")
    assert record.exc_info is None
    assert record.getMessage() == "rum error detail analytics failed failed_stage=error_detail error_type=HTTPError"
    assert "secret-query-body" not in record.getMessage()


def test_list_errors_degrades_without_control():
    page = ErrorsService(control=UnavailableControl(), issues=MemoryIssueStore()).list_errors("tester", {"range": "24h"})
    assert page["controlUnavailable"] is True


def test_patch_issue_triage():
    service = ErrorsService(control=MemoryControl(), issues=MemoryIssueStore())
    updated = service.patch_issue(
        "tester",
        "fp-1",
        {"status": "resolved", "note": "fixed", "resolvedVersion": "1.2.3"},
    )
    assert updated["status"] == "resolved"
    assert updated["note"] == "fixed"
    assert updated["resolvedVersion"] == "1.2.3"
    assert updated["resolvedAt"]


def test_restore_sourcemap_missing_release():
    control = MemoryControl()
    _seed_app(control)
    result = ErrorsService(control=control, sourcemaps=MemorySourcemapStore()).restore_sourcemap(
        "tester",
        {
            "application": "checkout",
            "frames": [{"filename": "asset:abc", "line": 1, "column": 1}],
        },
    )
    assert result["outcome"] == OUTCOME_MISSING_RELEASE


def test_restore_sourcemap_resolves_frames():
    control = MemoryControl()
    _seed_app(control)
    maps = MemorySourcemapStore()
    content = b'{"version":3,"file":"out.js","sources":["src/checkout.ts"],"names":["boom"],"mappings":"AAAAA"}'
    maps.save("checkout", "1.0.0", "asset:9ab0ce4d26f7d0ad959edd4b45878c1b", content)
    result = ErrorsService(control=control, sourcemaps=maps).restore_sourcemap(
        "tester",
        {
            "application": "checkout",
            "release": "1.0.0",
            "frames": [
                {
                    "filename": "asset:9ab0ce4d26f7d0ad959edd4b45878c1b",
                    "function": "a",
                    "line": 1,
                    "column": 1,
                }
            ],
        },
    )
    assert result["outcome"] == OUTCOME_RESOLVED
    assert result["anyResolved"] is True
    assert result["frames"][0]["file"] == "src/checkout.ts"
    assert result["frames"][0]["functionName"] == "boom"
    assert result["frames"][0]["resolved"] is True


def test_restore_frames_invalid_map():
    result = restore_frames(
        [{"filename": "asset:a", "line": 1, "column": 1}],
        b"not-json",
        "map-1",
    )
    assert result["outcome"] == "invalid_map"
