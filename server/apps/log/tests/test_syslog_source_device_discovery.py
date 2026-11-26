import logging
from datetime import datetime, timedelta, timezone

import pytest

from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.models import SyslogSourceDevice
from apps.log.services.syslog_source_device import (
    DISCOVER_FAILED,
    DISCOVER_FINISHED,
    DISCOVER_SKIPPED,
    DISCOVER_STARTED,
    DISCOVER_TRUNCATED,
    build_syslog_stats_query,
    discover_syslog_source_devices,
)
from apps.node_mgmt.models.cloud_region import CloudRegion

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)
SECRET = "HOSTNAME_SENTINEL_do_not_log"
QUERY_SECRET = "QUERY_BODY_SENTINEL_do_not_log"


class FakeAPI:
    def __init__(self, rows_by_region=None, errors=None):
        self.rows_by_region = rows_by_region or {}
        self.errors = errors or {}
        self.calls = []

    def query(self, query, start, end, limit=10):
        self.calls.append({"query": query, "start": start, "end": end, "limit": limit})
        for region_id, exc in self.errors.items():
            if f'cloud_region_id:"{region_id}"' in query:
                raise exc
        for region_id, rows in self.rows_by_region.items():
            if f'cloud_region_id:"{region_id}"' in query:
                return rows
        return []


def _install(monkeypatch, fake):
    monkeypatch.setattr("apps.log.services.syslog_source_device.VictoriaMetricsAPI", lambda: fake)


def _row(region_id, source_ip, hostname, first_seen, last_seen):
    return {
        "cloud_region_id": str(region_id),
        "source_ip": source_ip,
        "hostname": hostname,
        "first_seen": first_seen,
        "last_seen": last_seen,
    }


def _seen(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _log_text(caplog):
    formatter = logging.Formatter()
    return "\n".join(formatter.format(record) for record in caplog.records if record.name == "log")


@pytest.mark.django_db
def test_repeat_window_moves_last_seen_later_and_first_seen_earlier(monkeypatch):
    region = CloudRegion.objects.create(name="syslog-region")
    fake = FakeAPI(
        {
            region.id: [
                _row(region.id, "10.0.0.8", "  router  ", "2026-11-25T07:52:00Z", "2026-11-25T07:54:00Z"),
                _row(region.id, "10.0.0.8", "-", "2026-11-25T07:51:00Z", "2026-11-25T07:53:00Z"),
                _row(region.id, "10.0.0.8", None, "2026-11-25T07:50:00Z", "2026-11-25T07:52:00Z"),
                _row(region.id, "10.0.0.8", "   ", "2026-11-25T07:49:00Z", "2026-11-25T07:51:00Z"),
                _row(region.id, "  ", "ignored", "2026-11-25T07:49:00Z", "2026-11-25T07:51:00Z"),
                _row(region.id, "10.0.0.9", "kept", "", "2026-11-25T07:51:00Z"),
            ]
        }
    )
    _install(monkeypatch, fake)

    first = discover_syslog_source_devices(now=NOW)

    assert first == {"region_count": 1, "written_rows": 3, "truncated_regions": 0, "failed": False}
    stored = {(row.source_ip, row.hostname): (row.first_seen, row.last_seen) for row in SyslogSourceDevice.objects.all()}
    assert stored[("10.0.0.8", "router")] == (_seen("2026-11-25T07:52:00Z"), _seen("2026-11-25T07:54:00Z"))
    assert stored[("10.0.0.8", "")] == (_seen("2026-11-25T07:49:00Z"), _seen("2026-11-25T07:52:00Z"))
    assert stored[("10.0.0.8", "-")] == (_seen("2026-11-25T07:51:00Z"), _seen("2026-11-25T07:53:00Z"))
    assert ("10.0.0.9", "kept") not in stored
    assert fake.calls[0]["query"] == build_syslog_stats_query(region.id)
    assert fake.calls[0]["start"] == int((NOW - timedelta(minutes=10)).timestamp())
    assert fake.calls[0]["end"] == int(NOW.timestamp())
    assert fake.calls[0]["limit"] == VictoriaLogsConstants.QUERY_LIMIT_MAX

    fake.rows_by_region[region.id] = [
        _row(region.id, "10.0.0.8", "router", "2026-11-25T07:53:00Z", "2026-11-25T07:56:00Z"),
    ]
    discover_syslog_source_devices(now=NOW)
    router = SyslogSourceDevice.objects.get(source_ip="10.0.0.8", hostname="router")
    assert router.first_seen == _seen("2026-11-25T07:52:00Z")
    assert router.last_seen == _seen("2026-11-25T07:56:00Z")

    fake.rows_by_region[region.id] = [
        _row(region.id, "10.0.0.8", "router", "2026-11-25T07:40:00Z", "2026-11-25T07:50:00Z"),
    ]
    discover_syslog_source_devices(now=NOW)
    router.refresh_from_db()
    assert router.first_seen == _seen("2026-11-25T07:40:00Z")
    assert router.last_seen == _seen("2026-11-25T07:56:00Z")
    assert SyslogSourceDevice.objects.filter(source_ip="10.0.0.8", hostname="").count() == 1
    assert SyslogSourceDevice.objects.filter(hostname="-").count() == 1


@pytest.mark.django_db
def test_empty_result_and_unknown_region_keep_existing_rows(monkeypatch):
    region = CloudRegion.objects.create(name="known-region")
    SyslogSourceDevice.objects.create(
        cloud_region_id="missing-region",
        source_ip="10.1.1.1",
        hostname=SECRET,
        first_seen=_seen("2026-11-25T07:00:00Z"),
        last_seen=_seen("2026-11-25T07:10:00Z"),
    )
    fake = FakeAPI({region.id: []})
    _install(monkeypatch, fake)

    result = discover_syslog_source_devices(now=NOW)

    assert result["failed"] is False
    assert result["written_rows"] == 0
    assert [call["query"] for call in fake.calls] == [build_syslog_stats_query(region.id)]
    assert SyslogSourceDevice.objects.filter(hostname=SECRET).count() == 1


@pytest.mark.django_db
def test_query_error_keeps_rows_and_logs_one_safe_traceback(monkeypatch, caplog):
    first = CloudRegion.objects.create(name="region-a")
    second = CloudRegion.objects.create(name="region-b")
    existing = SyslogSourceDevice.objects.create(
        cloud_region_id=str(second.id),
        source_ip="10.2.2.2",
        hostname=SECRET,
        first_seen=_seen("2026-11-25T07:00:00Z"),
        last_seen=_seen("2026-11-25T07:10:00Z"),
    )
    held = {}

    class ExplodingAPI(FakeAPI):
        def query(self, query, start, end, limit=10):
            self.calls.append({"query": query, "start": start, "end": end, "limit": limit})
            if f'cloud_region_id:"{second.id}"' in query:
                exc = RuntimeError(QUERY_SECRET)
                held["exc"] = exc
                raise exc
            if f'cloud_region_id:"{first.id}"' in query:
                return [_row(first.id, "10.0.0.1", "edge", "2026-11-25T07:50:00Z", "2026-11-25T07:55:00Z")]
            return []

    fake = ExplodingAPI()
    _install(monkeypatch, fake)
    caplog.set_level(logging.INFO, logger="log")

    result = discover_syslog_source_devices(now=NOW)

    assert result["failed"] is True
    assert result["written_rows"] == 1
    assert SyslogSourceDevice.objects.filter(cloud_region_id=str(first.id), hostname="edge").exists()
    existing.refresh_from_db()
    assert existing.hostname == SECRET
    errors = [record for record in caplog.records if record.name == "log" and record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == DISCOVER_FAILED
    assert errors[0].args == (str(second.id), "query", "RuntimeError")
    assert errors[0].exc_info[2] is held["exc"].__traceback__
    assert held["exc"].args == (QUERY_SECRET,)
    formatted = logging.Formatter().format(errors[0])
    assert formatted.count("Traceback (most recent call last)") == 1
    assert QUERY_SECRET not in formatted
    assert SECRET not in _log_text(caplog)
    assert not any(record.msg == DISCOVER_FINISHED for record in caplog.records)
    assert any(record.msg == DISCOVER_STARTED for record in caplog.records)


@pytest.mark.django_db
def test_truncated_region_warns_and_keeps_unseen_rows(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="busy-region")
    SyslogSourceDevice.objects.create(
        cloud_region_id=str(region.id),
        source_ip="10.9.9.9",
        hostname="already",
        first_seen=_seen("2026-11-25T06:00:00Z"),
        last_seen=_seen("2026-11-25T06:05:00Z"),
    )
    monkeypatch.setattr(VictoriaLogsConstants, "QUERY_LIMIT_MAX", 1)
    fake = FakeAPI({region.id: [_row(region.id, "10.0.0.4", SECRET, "2026-11-25T07:50:00Z", "2026-11-25T07:55:00Z")]})
    _install(monkeypatch, fake)
    caplog.set_level(logging.INFO, logger="log")

    result = discover_syslog_source_devices(now=NOW)

    assert result == {"region_count": 1, "written_rows": 1, "truncated_regions": 1, "failed": False}
    assert fake.calls[0]["limit"] == 1
    assert SyslogSourceDevice.objects.filter(hostname="already").exists()
    assert SyslogSourceDevice.objects.filter(hostname=SECRET).exists()
    warnings = [record for record in caplog.records if record.name == "log" and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].msg == DISCOVER_TRUNCATED
    assert warnings[0].args == (str(region.id), 1)
    assert warnings[0].getMessage() == f"event=syslog_source_device_query_truncated truncated=true cloud_region_id={region.id} row_count=1"
    finish = next(record for record in caplog.records if record.msg == DISCOVER_FINISHED)
    assert finish.args == (1, 1, 1)
    assert SECRET not in _log_text(caplog)


@pytest.mark.django_db
def test_unusable_rows_are_skipped_without_logging_their_values(monkeypatch, caplog):
    region = CloudRegion.objects.create(name="skip-region")
    monkeypatch.setattr(VictoriaLogsConstants, "QUERY_LIMIT_MAX", 10)
    long_hostname = "h" * 256
    seen = int(datetime(2026, 11, 25, 7, 50, tzinfo=timezone.utc).timestamp())
    fake = FakeAPI(
        {
            region.id: [
                _row(region.id, "10.0.0.3", long_hostname, "2026-11-25T07:50:00Z", "2026-11-25T07:55:00Z"),
                {
                    "cloud_region_id": "",
                    "source_ip": "10.0.0.5",
                    "hostname": SECRET,
                    "first_seen": seen,
                    "last_seen": seen + 30,
                },
                _row(region.id, "10.0.0.6", "ok", seen, seen + 60),
            ]
        }
    )
    _install(monkeypatch, fake)
    caplog.set_level(logging.INFO, logger="log")

    result = discover_syslog_source_devices(now=NOW)

    assert result["written_rows"] == 1
    assert result["failed"] is False
    stored = SyslogSourceDevice.objects.get()
    assert stored.hostname == "ok"
    assert stored.first_seen == datetime(2026, 11, 25, 7, 50, tzinfo=timezone.utc)
    assert stored.last_seen == datetime(2026, 11, 25, 7, 51, tzinfo=timezone.utc)
    skipped = next(record for record in caplog.records if record.msg == DISCOVER_SKIPPED)
    assert skipped.args == (2,)
    rendered = _log_text(caplog)
    assert long_hostname not in rendered
    assert SECRET not in rendered


@pytest.mark.django_db
def test_no_cloud_regions_does_not_query_or_delete(monkeypatch):
    SyslogSourceDevice.objects.create(
        cloud_region_id="8",
        source_ip="10.8.8.8",
        hostname="",
        first_seen=_seen("2026-11-25T07:00:00Z"),
        last_seen=_seen("2026-11-25T07:05:00Z"),
    )
    fake = FakeAPI()
    _install(monkeypatch, fake)

    result = discover_syslog_source_devices(now=NOW)

    assert result == {"region_count": 0, "written_rows": 0, "truncated_regions": 0, "failed": False}
    assert fake.calls == []
    assert SyslogSourceDevice.objects.filter(hostname="").count() == 1
