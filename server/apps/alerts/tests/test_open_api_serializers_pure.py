from datetime import datetime
from datetime import timezone as dt_tz
from types import SimpleNamespace

import pytest

from apps.alerts.open_api.errors import AlertsOpenAPIError
from apps.alerts.open_api.serializers import (
    parse_batch_payload,
    parse_operator_payload,
    parse_ordering,
    parse_pagination,
    serialize_alert,
    serialize_event,
)


def test_parse_pagination_defaults_and_cap():
    assert parse_pagination({}) == (1, 20)
    assert parse_pagination({"page": "2", "page_size": "50"}) == (2, 50)
    assert parse_pagination({"page_size": "999"}) == (1, 100)


def test_parse_pagination_gateway_cap():
    assert parse_pagination({"page_size": "500"}, max_page_size=500) == (1, 500)
    assert parse_pagination({"page_size": "999"}, max_page_size=500) == (1, 500)


def test_parse_pagination_rejects_invalid():
    with pytest.raises(AlertsOpenAPIError) as exc:
        parse_pagination({"page": "0"})
    assert exc.value.code == "alerts.validation.failed"


def test_parse_ordering_defaults_and_allowed():
    assert parse_ordering({}) == "-created_at"
    assert parse_ordering({"ordering": "created_at"}) == "created_at"
    assert parse_ordering({"ordering": "-created_at"}) == "-created_at"


def test_parse_ordering_rejects_invalid():
    with pytest.raises(AlertsOpenAPIError) as exc:
        parse_ordering({"ordering": "-updated_at"})
    assert exc.value.code == "alerts.validation.failed"


def test_serialize_alert_hides_db_id_and_events():
    alert = SimpleNamespace(
        alert_id="ALERT-1",
        title="t",
        content="c",
        status="pending",
        level="warning",
        source_name="prom",
        operator=["alice"],
        item="cpu",
        resource_id="r1",
        resource_type="host",
        resource_name="h1",
        rule_id="rule-1",
        fingerprint="fp",
        dimensions={},
        first_event_time=datetime(2026, 8, 1, 12, 0, tzinfo=dt_tz.utc),
        last_event_time=datetime(2026, 8, 1, 12, 5, tzinfo=dt_tz.utc),
        closed_at=None,
        created_at=datetime(2026, 8, 1, 12, 0, tzinfo=dt_tz.utc),
        updated_at=datetime(2026, 8, 1, 12, 5, tzinfo=dt_tz.utc),
        labels={"k": "v"},
        enrichment={"e": 1},
        event_count_annotated=3,
        id=99,
    )
    listed = serialize_alert(alert, detail=False)
    assert listed["alert_id"] == "ALERT-1"
    assert listed["event_count"] == 3
    assert listed["closed_at"] is None
    assert "id" not in listed
    assert "events" not in listed
    assert "labels" not in listed
    detailed = serialize_alert(alert, detail=True)
    assert detailed["labels"] == {"k": "v"}
    assert detailed["enrichment"] == {"e": 1}


def test_serialize_event_exposes_source_name():
    event = SimpleNamespace(
        event_id="EVENT-1",
        title="cpu high",
        description="desc",
        level="warning",
        action="created",
        status="received",
        source=SimpleNamespace(id=5, name="prometheus"),
        resource_id="r1",
        resource_type="host",
        resource_name="h1",
        item="cpu",
        value=95.0,
        start_time=datetime(2026, 8, 1, 12, 0, tzinfo=dt_tz.utc),
        end_time=None,
        received_at=datetime(2026, 8, 1, 12, 1, tzinfo=dt_tz.utc),
    )
    payload = serialize_event(event)
    assert payload["event_id"] == "EVENT-1"
    assert payload["source"] == 5
    assert payload["source_name"] == "prometheus"
    assert payload["end_time"] is None


def test_serialize_event_source_name_empty_without_source():
    event = SimpleNamespace(
        event_id="EVENT-2",
        title="t",
        description=None,
        level="info",
        action="created",
        status="received",
        source=None,
        resource_id=None,
        resource_type=None,
        resource_name=None,
        item=None,
        value=None,
        start_time=datetime(2026, 8, 1, 12, 0, tzinfo=dt_tz.utc),
        end_time=None,
        received_at=datetime(2026, 8, 1, 12, 1, tzinfo=dt_tz.utc),
    )
    payload = serialize_event(event)
    assert payload["source"] is None
    assert payload["source_name"] == ""
    assert payload["description"] == ""


def test_parse_operator_assign_requires_assignee():
    with pytest.raises(AlertsOpenAPIError) as exc:
        parse_operator_payload("assign", {})
    assert exc.value.code == "alerts.validation.failed"
    data = parse_operator_payload("assign", {"assignee": ["alice"], "assignment_id": 3})
    assert data["assignee"] == ["alice"]
    assert data["assignment_id"] == 3


def test_parse_operator_acknowledge_allows_empty():
    assert parse_operator_payload("acknowledge", {}) == {}


def test_parse_operator_close_optional_reason():
    assert parse_operator_payload("close", {}) == {}
    assert parse_operator_payload("close", {"reason": "done"}) == {"reason": "done"}


def test_parse_batch_payload_merges_operator_fields():
    payload = parse_batch_payload(
        "assign",
        {"alert_ids": ["ALERT-1", "ALERT-2"], "assignee": ["alice"]},
    )
    assert payload["alert_ids"] == ["ALERT-1", "ALERT-2"]
    assert payload["assignee"] == ["alice"]


def test_parse_batch_payload_rejects_empty_alert_ids():
    with pytest.raises(AlertsOpenAPIError) as exc:
        parse_batch_payload("acknowledge", {"alert_ids": []})
    assert exc.value.code == "alerts.validation.failed"


def test_parse_batch_payload_rejects_too_many_alert_ids():
    with pytest.raises(AlertsOpenAPIError) as exc:
        parse_batch_payload("acknowledge", {"alert_ids": [f"ALERT-{index}" for index in range(101)]})
    assert exc.value.code == "alerts.validation.failed"
