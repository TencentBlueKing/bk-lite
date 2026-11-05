from datetime import datetime, timezone
from types import SimpleNamespace

from apps.monitor.services.process_health import (
    PROCESS_OBJECT_NAME,
    STATUS_HEALTHY,
    STATUS_NO_DATA,
    STATUS_UNHEALTHY,
    build_process_health_rows,
    empty_process_health_snapshot,
    process_alert_query_ids,
    process_id_aliases,
    reporting_process_ids,
    storage_id_from_process_labels,
)

NOW = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
TELEGRAF = SimpleNamespace(
    id="('host1', 'telegraf')",
    name="telegraf-AAXCEMON01-Monitoring Active",
    ip="172.24.210.1",
    interval=10,
    monitor_object=SimpleNamespace(name=PROCESS_OBJECT_NAME),
)
OBSERVER = SimpleNamespace(
    id="('host2', 'observer')",
    name="observer-AAXCEDBS01-Database OBServer01",
    ip="172.24.210.16",
    interval=10,
    monitor_object=SimpleNamespace(name=PROCESS_OBJECT_NAME),
)
HAPROXY = SimpleNamespace(
    id="('host3', 'haproxy')",
    name="haproxy-AAXCEDBS06-Database HAProxy01",
    ip="172.24.210.21",
    interval=10,
    monitor_object=SimpleNamespace(name=PROCESS_OBJECT_NAME),
)


def test_empty_selection_is_empty_list():
    assert empty_process_health_snapshot() == []
    assert build_process_health_rows(instances=[], reporting_ids=["x"], alerting_ids=["x"]) == []


def test_process_health_splits_reporting_alerting_and_no_data():
    rows = build_process_health_rows(
        instances=[TELEGRAF, OBSERVER, HAPROXY],
        reporting_ids=["('host1', 'telegraf')", "('host2', 'observer')"],
        alerting_ids=["('host2', 'observer')", "('host3', 'haproxy')"],
    )
    by_name = {row["process_name"]: row for row in rows}
    assert by_name["telegraf"]["status"] == STATUS_HEALTHY
    assert by_name["observer"]["status"] == STATUS_UNHEALTHY
    assert by_name["haproxy"]["status"] == STATUS_NO_DATA
    assert by_name["telegraf"]["app_name"] == "telegraf-AAXCEMON01-Monitoring Active"
    assert by_name["telegraf"]["host_name"] == "AAXCEMON01-Monitoring Active"


def test_process_health_ignores_host_level_alerts():
    rows = build_process_health_rows(
        instances=[TELEGRAF],
        reporting_ids=["('host1', 'telegraf')"],
        alerting_ids=["host1", "('host1',)"],
    )
    assert rows == [
        {
            "app_name": "telegraf-AAXCEMON01-Monitoring Active",
            "process_name": "telegraf",
            "host_name": "AAXCEMON01-Monitoring Active",
            "host_id": "host1",
            "ip": "172.24.210.1",
            "instance_id": "('host1', 'telegraf')",
            "status": STATUS_HEALTHY,
        }
    ]


def test_process_alert_query_ids_do_not_include_host_logical_id():
    ids = process_alert_query_ids([TELEGRAF, OBSERVER])
    assert "('host1', 'telegraf')" in ids
    assert "host1" not in ids
    assert "('host1',)" not in ids


def test_process_id_aliases_keep_tuple_storage_only():
    aliases = process_id_aliases("('host1', 'telegraf')")
    assert "('host1', 'telegraf')" in aliases
    assert "host1" not in aliases


def test_storage_id_from_process_labels_uses_host_and_process_name():
    assert storage_id_from_process_labels({"instance_id": "host1", "process_name": "telegraf"}) == "('host1', 'telegraf')"
    assert storage_id_from_process_labels({"instance_id": "host1"}) == ""


def test_reporting_process_ids_respect_lookback():
    series = [
        {
            "metric": {"instance_id": "host1", "process_name": "telegraf"},
            "value": [NOW.timestamp(), "8.0"],
        },
        {
            "metric": {"instance_id": "host2", "process_name": "observer"},
            "value": [NOW.timestamp() - 120, "40.0"],
        },
    ]
    found = reporting_process_ids(
        series,
        selected_ids=["('host1', 'telegraf')", "('host2', 'observer')"],
        interval_by_id={"('host1', 'telegraf')": 10, "('host2', 'observer')": 10},
        now=NOW,
    )
    assert found == {"('host1', 'telegraf')"}
