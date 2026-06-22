"""告警/事故过滤器覆盖测试。

对照 spec/prd/告警中心：列表支持按级别/状态/告警源等多条件过滤。
"""

import pytest

from apps.alerts.filters.alert import AlertModelFilter
from apps.alerts.filters.incident import IncidentModelFilter
from apps.alerts.models.models import Alert, Incident


@pytest.mark.django_db
def test_alert_filter_level_multi():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    Alert.objects.create(alert_id="A2", level="1", title="t", content="c", fingerprint="fp")
    Alert.objects.create(alert_id="A3", level="2", title="t", content="c", fingerprint="fp")
    qs = Alert.objects.all()
    assert AlertModelFilter().filter_level(qs, "level", "0,1").count() == 2
    # 空值返回原查询集
    assert AlertModelFilter().filter_level(qs, "level", "").count() == 3


@pytest.mark.django_db
def test_alert_filter_status_multi():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", status="pending")
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", status="closed")
    qs = Alert.objects.all()
    assert AlertModelFilter().filter_status(qs, "status", "pending").count() == 1


@pytest.mark.django_db
def test_alert_filter_source_name():
    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", source_name="prometheus")
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", source_name="zabbix")
    qs = Alert.objects.all()
    assert AlertModelFilter().filter_source_name(qs, "source_name", "prometheus").count() == 1


@pytest.mark.django_db
def test_alert_filter_activate_excludes_closed():
    from apps.alerts.constants.constants import AlertStatus

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", status="pending")
    closed_status = list(AlertStatus.CLOSED_STATUS)[0]
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp", status=closed_status)
    qs = Alert.objects.all()
    result = AlertModelFilter().filter_activate(qs, "activate", "true")
    assert "A1" in set(result.values_list("alert_id", flat=True))
    assert "A2" not in set(result.values_list("alert_id", flat=True))


@pytest.mark.django_db
def test_alert_filter_has_incident():
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    Alert.objects.create(alert_id="A2", level="0", title="t", content="c", fingerprint="fp")
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp")
    incident.alert.add(alert)
    qs = Alert.objects.all()
    assert AlertModelFilter().filter_incident(qs, "has_incident", "true").count() == 1
    assert AlertModelFilter().filter_incident(qs, "has_incident", "false").count() == 1


# --------------------------------------------------------------------------
# IncidentModelFilter
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_incident_filter_level_and_status():
    Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", status="pending")
    Incident.objects.create(incident_id="I2", level="1", title="t", fingerprint="fp", status="closed")
    qs = Incident.objects.all()
    assert IncidentModelFilter.filter_level(qs, "level", "0").count() == 1
    assert IncidentModelFilter.filter_status(qs, "status", "pending,closed").count() == 2
    assert IncidentModelFilter.filter_level(qs, "level", "").count() == 2
