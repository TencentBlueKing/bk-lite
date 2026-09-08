from datetime import datetime

import duckdb
import pytest

from apps.alerts.aggregation.processor.aggregation_processor import AggregationProcessor
from apps.alerts.aggregation.query.builder import SQLBuilder
from apps.alerts.aggregation.window.factory import WindowConfig, WindowType
from apps.alerts.filters.alert import AlertModelFilter
from apps.alerts.models.models import Alert
from apps.alerts.utils.rule_matcher import RuleMatcher


@pytest.mark.django_db
def test_alert_filter_and_assignment_match_enrichment_path():
    alice = Alert.objects.create(
        alert_id="A-enrich-alice",
        fingerprint="fp-enrich-alice",
        level="1",
        title="CPU high",
        content="cpu",
        enrichment={"cmdb": {"owner": "alice"}},
    )
    Alert.objects.create(
        alert_id="A-enrich-bob",
        fingerprint="fp-enrich-bob",
        level="1",
        title="CPU high",
        content="cpu",
        enrichment={"cmdb": {"owner": "bob"}},
    )

    filtered = AlertModelFilter(
        data={
            "enrichment_key": "enrichment.cmdb.owner",
            "enrichment_value": "alice",
        },
        queryset=Alert.objects.all(),
    ).qs
    assigned = RuleMatcher({}).filter_queryset(
        Alert.objects.all(),
        [[{"key": "enrichment.cmdb.owner", "operator": "eq", "value": "alice"}]],
    )

    assert list(filtered.values_list("id", flat=True)) == [alice.id]
    assert assigned == [alice.id]


@pytest.mark.django_db
def test_alert_filter_and_assignment_dual_read_legacy_namespace_array():
    legacy = Alert.objects.create(
        alert_id="A-enrich-legacy",
        fingerprint="fp-enrich-legacy",
        level="1",
        title="CPU high",
        content="cpu",
        enrichment={"cmdb": [{"owner": "alice"}, {"owner": "bob"}]},
    )

    filtered = AlertModelFilter(
        data={"enrichment_key": "enrichment.cmdb.owner", "enrichment_value": "alice"},
        queryset=Alert.objects.all(),
    ).qs
    assigned = RuleMatcher({}).filter_queryset(
        Alert.objects.all(),
        [[{"key": "enrichment.cmdb.owner", "operator": "eq", "value": "alice"}]],
    )

    assert list(filtered.values_list("id", flat=True)) == [legacy.id]
    assert assigned == [legacy.id]


@pytest.mark.django_db
def test_alert_filter_rejects_enrichment_path_injection():
    Alert.objects.create(
        alert_id="A-injection",
        fingerprint="fp-injection",
        level="1",
        title="CPU high",
        content="cpu",
        enrichment={"cmdb": {"owner": "alice"}},
    )

    queryset = AlertModelFilter(
        data={"enrichment_key": "enrichment.cmdb.owner'); DROP TABLE alerts_alert;--"},
        queryset=Alert.objects.all(),
    ).qs

    assert queryset.count() == 0


def test_aggregation_dimension_validation_accepts_enrichment_and_rejects_injection():
    assert AggregationProcessor._validate_dimensions(["enrichment.cmdb.owner"], "owner-rule") == ["enrichment.cmdb.owner"]
    assert AggregationProcessor._validate_dimensions(["enrichment.cmdb.owner')"], "unsafe-rule") == ["event_id"]


def test_duckdb_groups_events_by_enrichment_dimension(monkeypatch):
    monkeypatch.setattr(
        WindowConfig,
        "get_window_start",
        lambda self: datetime.fromisoformat("2026-09-03T08:00:00+00:00"),
    )
    sql = SQLBuilder().build_aggregation_sql(
        dimensions=["enrichment.cmdb.owner"],
        window_config=WindowConfig(WindowType.SLIDING, window_size_minutes=10),
        strategy_id=9,
    )
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE events_table AS SELECT * FROM (VALUES
          ('E1', 'CPU', 'high', '1', 'host-a', 'ext-a', TIMESTAMP '2026-09-03 09:00:00', 'created', '{"cmdb":{"owner":"alice"}}'),
          ('E2', 'CPU', 'high', '1', 'host-b', 'ext-b', TIMESTAMP '2026-09-03 09:00:00', 'created', '{"cmdb":{"owner":"bob"}}')
        ) AS t(event_id, title, description, level, resource_name, external_id, received_at, action, enrichment)
        """
    )

    rows = connection.execute(sql).fetchall()

    assert len(rows) == 2
    assert {row[1] for row in rows} == {
        "enrichment.cmdb.owner=alice",
        "enrichment.cmdb.owner=bob",
    }


def test_duckdb_reads_legacy_namespace_array_dimension(monkeypatch):
    monkeypatch.setattr(
        WindowConfig,
        "get_window_start",
        lambda self: datetime.fromisoformat("2026-09-03T08:00:00+00:00"),
    )
    sql = SQLBuilder().build_aggregation_sql(
        dimensions=["enrichment.cmdb.owner"],
        window_config=WindowConfig(WindowType.SLIDING, window_size_minutes=10),
        strategy_id=9,
    )
    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE events_table AS SELECT * FROM (VALUES
          ('E1', 'CPU', 'high', '1', 'host-a', 'ext-a', TIMESTAMP '2026-09-03 09:00:00', 'created', '{"cmdb":[{"owner":"alice"},{"owner":"bob"}]}')
        ) AS t(event_id, title, description, level, resource_name, external_id, received_at, action, enrichment)
        """
    )

    rows = connection.execute(sql).fetchall()

    assert len(rows) == 1
    assert rows[0][1] == "enrichment.cmdb.owner=alice"
