"""Prometheus 告警源适配器覆盖测试。

对照 spec/prd/告警中心·集成：Prometheus Alertmanager webhook 负载归一化为标准事件。
"""

import pytest

from apps.alerts.common.source_adapter.prometheus import PrometheusAdapter
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Level


@pytest.fixture
def event_levels(db):
    from apps.alerts.constants.constants import LevelType

    for lid in (0, 1, 2, 3):
        Level.objects.create(level_id=lid, level_name=f"L{lid}", level_display_name=f"等级{lid}", level_type=LevelType.EVENT)


@pytest.fixture
def prom_source(db):
    return AlertSource.objects.create(
        name="prom", source_id="prom", source_type="prometheus", secret="sec",
        config={"event_fields_mapping": {}, "base_url": "http://prom:9090"},
    )


def _adapter(prom_source):
    return PrometheusAdapter(alert_source=prom_source)


@pytest.mark.django_db
def test_map_severity(event_levels, prom_source):
    a = _adapter(prom_source)
    assert a._map_prometheus_severity("critical") == "0"
    assert a._map_prometheus_severity("warning") == "1"
    assert a._map_prometheus_severity("info") == "2"
    assert a._map_prometheus_severity("unknown") == "3"
    assert a._map_prometheus_severity(None) == "3"


@pytest.mark.django_db
def test_map_status(event_levels, prom_source):
    a = _adapter(prom_source)
    assert a._map_prometheus_status("firing") == "created"
    assert a._map_prometheus_status("resolved") == "recovery"
    assert a._map_prometheus_status("other") == "created"


@pytest.mark.django_db
def test_iso_to_timestamp(event_levels, prom_source):
    a = _adapter(prom_source)
    assert a._iso_to_timestamp(None) is None
    assert a._iso_to_timestamp("not-a-date") is None
    ts = a._iso_to_timestamp("2026-01-01T00:00:00Z")
    assert ts is not None and ts.isdigit()


@pytest.mark.django_db
def test_build_external_id(event_levels, prom_source):
    a = _adapter(prom_source)
    assert a._build_external_id({}, {"external_id": "ext-1"}) == "ext-1"
    assert a._build_external_id({"external_id": "lab"}, {}) == "lab"
    assert a._build_external_id({}, {}) is None


def test_validate_config():
    assert PrometheusAdapter.validate_config({"base_url": "x"}) is True
    assert PrometheusAdapter.validate_config({}) is False


@pytest.mark.django_db
def test_normalize_payload_from_alerts(event_levels, prom_source):
    a = _adapter(prom_source)
    payload = {
        "receiver": "bk-lite",
        "commonLabels": {"team": "ops"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighCPU", "instance": "host1", "severity": "critical"},
                "annotations": {"description": "CPU超过90%"},
                "startsAt": "2026-01-01T00:00:00Z",
            }
        ],
    }
    events = a.normalize_payload(payload)
    assert len(events) == 1
    ev = events[0]
    assert "HighCPU" in ev["title"]
    assert ev["level"] == "0"
    assert ev["action"] == "created"
    assert ev["resource_name"] == "host1"


@pytest.mark.django_db
def test_normalize_payload_prefers_events(event_levels, prom_source):
    a = _adapter(prom_source)
    events = a.normalize_payload({"events": [{"title": "direct"}]})
    assert events == [{"title": "direct"}]


@pytest.mark.django_db
def test_normalize_payload_empty_raises(event_levels, prom_source):
    a = _adapter(prom_source)
    with pytest.raises(ValueError):
        a.normalize_payload({"alerts": []})


@pytest.mark.django_db
def test_get_integration_guide(event_levels, prom_source):
    a = _adapter(prom_source)
    guide = a.get_integration_guide("http://host")
    assert guide["source_type"] == "prometheus"
