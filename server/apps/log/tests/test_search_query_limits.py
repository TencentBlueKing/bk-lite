from datetime import datetime, timezone
from types import SimpleNamespace

from apps.log.constants.victoriametrics import VictoriaLogsConstants
from apps.log.nats.log import _build_paginated_alert_segments, _normalize_bounded_int, log_search
from apps.log.serializers.search import LogFieldValuesSerializer, LogHitsSerializer, LogSearchSerializer
from apps.log.utils.query_log import VictoriaMetricsAPI


def test_log_search_serializer_rejects_oversized_limit():
    serializer = LogSearchSerializer(data={"query": "*", "limit": VictoriaLogsConstants.QUERY_LIMIT_MAX + 1})

    assert not serializer.is_valid()
    assert "limit" in serializer.errors


def test_log_hits_serializer_rejects_oversized_fields_limit():
    serializer = LogHitsSerializer(
        data={
            "query": "*",
            "field": "_stream",
            "fields_limit": VictoriaLogsConstants.HITS_FIELDS_LIMIT_MAX + 1,
        }
    )

    assert not serializer.is_valid()
    assert "fields_limit" in serializer.errors


def test_log_field_values_serializer_rejects_oversized_limit():
    serializer = LogFieldValuesSerializer(
        data={
            "filed": "_stream",
            "limit": VictoriaLogsConstants.FIELD_VALUES_LIMIT_MAX + 1,
        }
    )

    assert not serializer.is_valid()
    assert "limit" in serializer.errors


def test_log_nats_search_rejects_oversized_limit_without_vm_query(monkeypatch):
    class FakeVictoriaMetricsAPI:
        def query(self, *args, **kwargs):
            raise AssertionError("VMLogs query should not be called")

    monkeypatch.setattr("apps.log.nats.log.VictoriaMetricsAPI", FakeVictoriaMetricsAPI)

    result = log_search(
        "*",
        ("2026-04-22 00:00:00", "2026-04-22 00:01:00"),
        limit=VictoriaLogsConstants.QUERY_LIMIT_MAX + 1,
    )

    assert result["result"] is False
    assert "limit" in result["message"]


def test_normalize_bounded_int_accepts_default():
    assert _normalize_bounded_int("", "limit", 10, 1000) == 10


def test_vmlogs_query_clamps_oversized_limit(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter(())

    def fake_post(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.post", fake_post)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.query("*", "start", "end", VictoriaLogsConstants.QUERY_LIMIT_MAX + 50)

    assert captured["limit"] == VictoriaLogsConstants.QUERY_LIMIT_MAX


def test_vmlogs_query_normalizes_wrapped_logsql_string(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter(())

    def fake_post(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.post", fake_post)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.query('"instance_id:\\"uuid\\""', "start", "end", 10)

    assert captured["query"] == 'instance_id:"uuid"'


def test_vmlogs_field_values_clamps_oversized_limit(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"values": []}

    def fake_get(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.get", fake_get)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.field_values("start", "end", "_stream", VictoriaLogsConstants.FIELD_VALUES_LIMIT_MAX + 25)

    assert captured["limit"] == VictoriaLogsConstants.FIELD_VALUES_LIMIT_MAX


def test_vmlogs_hits_clamps_oversized_fields_limit(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": []}

    def fake_post(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.post", fake_post)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.hits("*", "start", "end", "_stream", VictoriaLogsConstants.HITS_FIELDS_LIMIT_MAX + 5)

    assert captured["fields_limit"] == VictoriaLogsConstants.HITS_FIELDS_LIMIT_MAX


def test_vmlogs_hits_normalizes_wrapped_logsql_string(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"hits": []}

    def fake_post(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.post", fake_post)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.hits('"instance_id:\\"uuid\\""', "start", "end", "_stream", 5)

    assert captured["query"] == 'instance_id:"uuid"'


def test_vmlogs_field_values_normalizes_wrapped_logsql_string(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"values": []}

    def fake_get(url, params, **kwargs):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr("apps.log.utils.query_log.requests.get", fake_get)

    api = VictoriaMetricsAPI()
    api.host = "http://victorialogs.example"
    api.field_values("start", "end", "_stream", 100, '"instance_id:\\"uuid\\""')

    assert captured["query"] == 'instance_id:"uuid"'


class FakeAlertQuerySet:
    def __init__(self, alerts):
        self.alerts = alerts
        self.sliced = None

    def count(self):
        return len(self.alerts)

    def order_by(self, *fields):
        return self

    def __getitem__(self, value):
        self.sliced = value
        return self.alerts[value]


def _make_alert(alert_id):
    event_time = datetime(2026, 5, 6, 1, alert_id, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=alert_id,
        policy_id="policy-1",
        collect_type_id="ctype-1",
        source_id=f"source-{alert_id}",
        level="warning",
        value="1",
        content="content",
        status="active",
        start_event_time=event_time,
        end_event_time=event_time,
        created_at=event_time,
        updated_at=event_time,
    )


def test_alert_segments_are_sliced_before_building_response_items():
    queryset = FakeAlertQuerySet([_make_alert(idx) for idx in range(1, 6)])

    result = _build_paginated_alert_segments(queryset, page=2, page_size=2)

    assert queryset.sliced == slice(2, 4, None)
    assert result["count"] == 5
    assert [item["id"] for item in result["items"]] == [3, 4]
