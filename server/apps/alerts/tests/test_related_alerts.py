"""相关告警服务覆盖测试。

对照 specs/capabilities/legacy-prd-告警中心-告警.md：根据维度相似度推荐相关告警。
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.alerts.models.models import Alert, Incident
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


def _similar_alert(alert_id, fingerprint, now):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title="t",
        content="c",
        fingerprint=fingerprint,
        dimensions={"service": "svc"},
        team=[1],
        status="unassigned",
        last_event_time=now,
    )


def _incident(incident_id, title):
    return Incident.objects.create(
        incident_id=incident_id,
        level="0",
        title=title,
        fingerprint=incident_id,
    )


def _normalized_sql(sql):
    return sql.lower().replace('"', "").replace("`", "").replace("[", "").replace("]", "")


def _incident_select_count(captured):
    """统计 alerts_incident 与中间表 alerts_incident_alert 的 SELECT。同一条 JOIN 只计一次。"""
    count = 0
    for query in captured.captured_queries:
        sql = _normalized_sql(query["sql"])
        if not sql.startswith("select"):
            continue
        if "alerts_incident_update" in sql:
            continue
        if "alerts_incident" in sql:
            count += 1
    return count


def _summary_fields(summary):
    assert summary
    assert [set(item) for item in summary] == [{"id", "incident_id", "title"}] * len(summary)


@pytest.mark.django_db
def test_find_related_alerts_incident_selects_stay_flat():
    """N=1、10、100 时，事故表和中间表 SELECT 次数相同，且 limit=1 只返回 1 条。"""
    counts = []
    for candidate_count in (1, 10, 100):
        now = timezone.now()
        prefix = f"n{candidate_count}"
        base = _similar_alert(f"BASE-{prefix}", f"fpb{prefix}", now)
        current = _incident(f"IC-{prefix}", "当前事故")
        current.alert.add(base)
        candidates = []
        candidate_incidents = []
        for index in range(candidate_count):
            candidate = _similar_alert(f"C-{prefix}-{index}", f"fpc{prefix}{index}", now)
            incident = _incident(f"IR-{prefix}-{index}", f"候选事故{index}")
            incident.alert.add(candidate)
            candidates.append(candidate)
            candidate_incidents.append(incident)
        try:
            with CaptureQueriesContext(connection) as captured:
                result = RAS.find_related_alerts(base, limit=1, group_ids=[1])
            assert len(result["items"]) == 1
            _summary_fields(result["current_incidents"])
            assert result["current_incidents"][0]["incident_id"] == current.incident_id
            assert result["current_incidents"][0]["title"] == "当前事故"
            _summary_fields(result["items"][0]["incidents"])
            counts.append(_incident_select_count(captured))
        finally:
            alert_ids = [base.pk, *[item.pk for item in candidates]]
            incident_ids = [current.pk, *[item.pk for item in candidate_incidents]]
            Alert.objects.filter(pk__in=alert_ids).delete()
            Incident.objects.filter(pk__in=incident_ids).delete()

    # 修复前随候选数增长：[3, 12, 102] = 预取 1 次 + 当前告警 1 次 + 每个候选 1 次。
    # 修复后只保留那两次，三次测量相同。
    assert counts == [2, 2, 2], counts


@pytest.mark.django_db
def test_incident_summary_keeps_updated_at_and_id_order():
    """预取候选和未预取的当前告警都按 updated_at、id 降序返回事故摘要。"""
    now = timezone.now()
    newer = now - timedelta(minutes=1)
    tie = now - timedelta(minutes=5)
    base = _similar_alert("BASE-ORDER", "fp-base-order", now)
    candidate = _similar_alert("C-ORDER", "fp-cand-order", now)

    def _ordered_incidents(owner, prefix):
        low = _incident(f"{prefix}-low", "较早较小")
        high = _incident(f"{prefix}-high", "较早较大")
        latest = _incident(f"{prefix}-new", "较新")
        low.alert.add(owner)
        high.alert.add(owner)
        latest.alert.add(owner)
        Incident.objects.filter(pk=low.pk).update(updated_at=tie)
        Incident.objects.filter(pk=high.pk).update(updated_at=tie)
        Incident.objects.filter(pk=latest.pk).update(updated_at=newer)
        return [latest, high, low]

    expected_current = _ordered_incidents(base, "CUR")
    expected_candidate = _ordered_incidents(candidate, "CAN")
    result = RAS.find_related_alerts(base, limit=1, group_ids=[1])
    assert len(result["items"]) == 1
    assert result["items"][0]["alert_id"] == "C-ORDER"

    def _assert_order(summary, expected):
        _summary_fields(summary)
        assert [item["incident_id"] for item in summary] == [item.incident_id for item in expected]
        assert [item["id"] for item in summary] == [item.id for item in expected]
        assert [item["title"] for item in summary] == [item.title for item in expected]

    _assert_order(result["current_incidents"], expected_current)
    _assert_order(result["items"][0]["incidents"], expected_candidate)


@pytest.mark.django_db
def test_incident_summary_orders_unordered_view_prefetch():
    """AlertModelViewSet.get_queryset 无序 prefetch 当前告警时，摘要仍按 -updated_at,-id。"""
    now = timezone.now()
    newer = now - timedelta(minutes=1)
    tie = now - timedelta(minutes=5)
    base = _similar_alert("BASE-VIEW-PF", "fp-base-view-pf", now)
    _similar_alert("C-VIEW-PF", "fp-cand-view-pf", now)

    low = _incident("CUR-PF-low", "较早较小")
    high = _incident("CUR-PF-high", "较早较大")
    latest = _incident("CUR-PF-new", "较新")
    low.alert.add(base)
    high.alert.add(base)
    latest.alert.add(base)
    Incident.objects.filter(pk=low.pk).update(updated_at=tie)
    Incident.objects.filter(pk=high.pk).update(updated_at=tie)
    Incident.objects.filter(pk=latest.pk).update(updated_at=newer)

    base = Alert.objects.prefetch_related("incident_set").get(pk=base.pk)
    result = RAS.find_related_alerts(base, limit=1, group_ids=[1])
    summary = result["current_incidents"]
    _summary_fields(summary)
    assert [item["incident_id"] for item in summary] == [
        latest.incident_id,
        high.incident_id,
        low.incident_id,
    ]
    assert [item["id"] for item in summary] == [latest.id, high.id, low.id]
    assert [item["title"] for item in summary] == [latest.title, high.title, low.title]
