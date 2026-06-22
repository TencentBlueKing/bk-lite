"""相关告警服务覆盖测试。

对照 spec/prd/告警中心·告警：根据维度相似度推荐相关告警。
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.alerts.models.models import Alert
from apps.alerts.service.related_alerts import RelatedAlertsService as RAS


# --------------------------------------------------------------------------
# 纯函数
# --------------------------------------------------------------------------


def test_calculate_similarity_no_match():
    score, matched = RAS._calculate_similarity({"service": "a"}, {"service": "b"})
    assert score == 0
    assert matched == {}


def test_calculate_similarity_full_match():
    dims = {"service": "svc", "item": "cpu"}
    score, matched = RAS._calculate_similarity(dims, dims)
    assert score == 100
    assert matched == dims


def test_calculate_similarity_partial():
    score, matched = RAS._calculate_similarity(
        {"service": "svc", "item": "cpu"}, {"service": "svc", "item": "mem"}
    )
    # service priority 4 / (4+1) = 80
    assert score == 80
    assert matched == {"service": "svc"}


def test_calculate_similarity_empty():
    assert RAS._calculate_similarity({}, {"a": "1"}) == (0, {})


def test_get_match_reason_key_event():
    assert RAS._get_match_reason({"service": "x"}, 95) == "关键事件"


def test_get_match_reason_by_dimension():
    assert RAS._get_match_reason({"location": "x"}, 50) == "相同位置"
    assert RAS._get_match_reason({}, 30) == "相关告警"


def test_format_time_proximity():
    now = timezone.now()
    assert RAS._format_time_proximity(now, now) == "0秒内"
    assert RAS._format_time_proximity(now, now - timedelta(minutes=5)) == "5分钟前"
    assert RAS._format_time_proximity(now, now - timedelta(hours=2)) == "2小时前"
    assert RAS._format_time_proximity(None, now) == "--"


# --------------------------------------------------------------------------
# DB 相关
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_get_alert_dimensions_from_field():
    alert = Alert.objects.create(
        alert_id="A1", level="0", title="t", content="c", fingerprint="fp",
        dimensions={"service": "svc", "empty": ""},
    )
    dims = RAS._get_alert_dimensions(alert)
    assert dims == {"service": "svc"}


@pytest.mark.django_db
def test_get_incidents_summary():
    from apps.alerts.models.models import Incident

    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    incident = Incident.objects.create(incident_id="I1", level="0", title="事故1", fingerprint="fp")
    incident.alert.add(alert)
    summary = RAS._get_incidents_summary(alert)
    assert summary[0]["incident_id"] == "I1"


@pytest.mark.django_db
def test_find_related_alerts_no_dimensions_returns_empty():
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", dimensions={})
    result = RAS.find_related_alerts(alert, group_ids=[1])
    assert result["related_count"] == 0
    assert result["items"] == []


@pytest.mark.django_db
def test_find_related_alerts_finds_similar():
    now = timezone.now()
    base = Alert.objects.create(
        alert_id="A1", level="0", title="t", content="c", fingerprint="fp",
        dimensions={"service": "svc"}, team=[1], status="unassigned",
        last_event_time=now,
    )
    related = Alert.objects.create(
        alert_id="A2", level="0", title="t2", content="c", fingerprint="fp2",
        dimensions={"service": "svc"}, team=[1], status="unassigned",
        last_event_time=now,
    )
    result = RAS.find_related_alerts(base, group_ids=[1])
    ids = {item["alert_id"] for item in result["items"]}
    assert "A2" in ids
    assert result["related_count"] >= 1
