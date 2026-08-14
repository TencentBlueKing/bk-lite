from types import SimpleNamespace

import pytest

from apps.alerts.common.source_adapter import base
from apps.alerts.common.source_adapter.base import AlertSourceAdapter

pytestmark = pytest.mark.unit


class _ProbeAdapter(AlertSourceAdapter):
    def fetch_alerts(self):
        return []


class _SensitiveLookup(dict):
    def __init__(self, payload_marker, exception_marker):
        super().__init__(
            title="event",
            secret=payload_marker,
            labels={"sensitive": payload_marker},
        )
        self.exception_marker = exception_marker

    def get(self, key, default=None):
        if key == "service":
            raise RuntimeError(self.exception_marker)
        return super().get(key, default)


def _adapter(mapping):
    adapter = object.__new__(_ProbeAdapter)
    adapter.mapping = mapping
    adapter.unique_fields = ["title"]
    adapter.info_level = "3"
    adapter.levels = ["0", "1", "2", "3"]
    adapter.alert_source = SimpleNamespace(source_id="log-safety-probe")
    adapter.trusted_internal = False
    adapter.resolved_team = []
    return adapter


@pytest.fixture(autouse=True)
def _disable_enrichment(monkeypatch):
    enrichment = SimpleNamespace(enrich_batch=lambda events: None)
    monkeypatch.setattr(base, "EnrichmentEngine", lambda: enrichment)


def test_missing_required_field_log_excludes_event_payload(caplog):
    marker = "SECRET-MISSING-TITLE-4671"
    adapter = _adapter({"title": "title"})

    adapter.create_events([{"description": marker, "secret": marker}])

    assert marker not in caplog.text
    assert "source_id=log-safety-probe" in caplog.text
    assert "event_index=0" in caplog.text
    assert adapter.last_ingestion_result == {
        "received": 1,
        "accepted": 0,
        "skipped": 1,
        "errored": 0,
        "duplicates": 0,
        "rejected": 1,
    }


def test_mapping_error_log_excludes_payload_exception_and_traceback(caplog):
    payload_marker = "SECRET-MAPPING-PAYLOAD-4671"
    exception_marker = "SECRET-MAPPING-EXCEPTION-4671"
    adapter = _adapter({"title": "title", "service": "service"})

    adapter.create_events([_SensitiveLookup(payload_marker, exception_marker)])

    assert payload_marker not in caplog.text
    assert exception_marker not in caplog.text
    assert "Traceback" not in caplog.text
    assert "source_id=log-safety-probe" in caplog.text
    assert "event_index=0" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert adapter.last_ingestion_result["errored"] == 1


def test_conversion_error_log_excludes_payload_exception_and_traceback(caplog):
    payload_marker = "SECRET-CONVERSION-PAYLOAD-4671"
    exception_marker = "SECRET-CONVERSION-EXCEPTION-4671"
    adapter = _adapter({"title": "title", exception_marker: "secret"})

    adapter.create_events(
        [
            {
                "title": "event",
                "secret": payload_marker,
                "labels": {"sensitive": payload_marker},
            }
        ]
    )

    assert payload_marker not in caplog.text
    assert exception_marker not in caplog.text
    assert "Traceback" not in caplog.text
    assert "source_id=log-safety-probe" in caplog.text
    assert "event_index=0" in caplog.text
    assert "error_type=TypeError" in caplog.text
    assert adapter.last_ingestion_result["errored"] == 1


def test_failure_logs_keep_original_mixed_batch_indexes(caplog):
    marker = "SECRET-MIXED-BATCH-4671"
    adapter = _adapter({"title": "title", "service": "service"})

    adapter.create_events(
        [
            {"description": marker},
            _SensitiveLookup(marker, marker),
            {"title": "conversion failure"},
        ]
    )

    assert marker not in caplog.text
    assert "event_index=0" in caplog.text
    assert "event_index=1" in caplog.text
    assert "event_index=2" in caplog.text
    assert adapter.last_ingestion_result == {
        "received": 3,
        "accepted": 0,
        "skipped": 1,
        "errored": 2,
        "duplicates": 0,
        "rejected": 1,
    }
