"""事故序列化器 SerializerMethodField 覆盖测试。

对照 spec/prd/告警中心·事故：事故展示关联告警数、来源、处理人/协作者。
"""

from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Incident
from apps.alerts.serializers.incident import IncidentModelSerializer


def _ser(context=None):
    # 直接构造实例并附加 _context，绕过需要 request 的 __init__
    s = IncidentModelSerializer.__new__(IncidentModelSerializer)
    s._context = context or {}
    s.parent = None
    return s


@pytest.mark.django_db
def test_get_sources():
    src = AlertSource.objects.create(name="Zabbix", source_id="s1", source_type="zabbix", secret="x")
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    event = Event.objects.create(source=src, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1")
    alert.events.add(event)
    incident.alert.add(alert)
    assert IncidentModelSerializer.get_sources(incident) == "Zabbix"


@pytest.mark.django_db
def test_get_alert_count_fallback():
    incident = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    incident.alert.add(alert)
    assert IncidentModelSerializer.get_alert_count(incident) == 1


def test_get_operator_users_empty():
    obj = SimpleNamespace(operator=[])
    assert _ser().get_operator_users(obj) == ""


def test_get_operator_users_with_map():
    obj = SimpleNamespace(operator=["u1", "u2"])
    ser = _ser(context={"operator_user_map": {"u1": "用户1", "u2": "用户2"}})
    assert ser.get_operator_users(obj) == "用户1, 用户2"


def test_get_operator_users_string():
    obj = SimpleNamespace(operator="single")
    assert _ser().get_operator_users(obj) == "single"


def test_get_collaborator_users_empty():
    obj = SimpleNamespace(collaborators=[])
    assert _ser().get_collaborator_users(obj) == []


def test_get_collaborator_users_with_map():
    obj = SimpleNamespace(collaborators=["u1"])
    ser = _ser(context={"operator_user_map": {"u1": "用户1"}})
    result = ser.get_collaborator_users(obj)
    assert result == [{"username": "u1", "display_name": "用户1"}]


def test_get_duration_inactive():
    obj = SimpleNamespace(status="closed", created_at=timezone.now())
    assert IncidentModelSerializer.get_duration(obj) == "--"


def test_validate_team_no_request():
    ser = _ser(context={})
    assert ser.validate_team([1, 2]) == [1, 2]


def test_validate_team_empty():
    ser = _ser(context={})
    assert ser.validate_team([]) == []


def test_validate_team_superuser():
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True, group_list=[{"id": 1}]),
                             COOKIES={"current_team": "1"})
    ser = _ser(context={"request": request})
    assert ser.validate_team([1, 2]) == [1, 2]


def test_validate_operator_empty():
    ser = _ser(context={})
    assert ser.validate_operator([]) == []


def test_get_collaborator_users_non_list():
    obj = SimpleNamespace(collaborators="single")
    assert _ser().get_collaborator_users(obj) == []


def test_get_operator_users_non_list():
    obj = SimpleNamespace(operator=123)
    assert _ser().get_operator_users(obj) == ""


@pytest.mark.django_db
def test_serializer_create_with_alerts():
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    ser = IncidentModelSerializer.__new__(IncidentModelSerializer)
    incident = ser.create({"incident_id": "I1", "level": "0", "title": "新事故", "alert": [alert]})
    assert incident.alert.filter(id=alert.id).exists()


@pytest.mark.django_db
def test_serializer_update_with_alerts():
    incident = Incident.objects.create(incident_id="I1", level="0", title="旧", fingerprint="fp")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    ser = IncidentModelSerializer.__new__(IncidentModelSerializer)
    updated = ser.update(incident, {"title": "新", "alert": [alert]})
    assert updated.title == "新"
    assert updated.alert.filter(id=alert.id).exists()
