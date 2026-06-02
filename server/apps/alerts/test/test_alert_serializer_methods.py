"""告警序列化器方法补充覆盖测试。

对照 spec/prd/告警中心·告警：告警展示处理人、通知状态、来源、事件数。
"""

from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.models import Alert
from apps.alerts.serializers.alert import AlertModelSerializer


def _ser(context=None, notify_map=None):
    s = AlertModelSerializer.__new__(AlertModelSerializer)
    s._context = context or {}
    s.parent = None
    s.alert_notify_result_map = notify_map or {}
    return s


@pytest.mark.django_db
def test_set_alert_notify_result_map_empty_for_non_iterable():
    assert AlertModelSerializer.set_alert_notify_result_map(None) == {}


@pytest.mark.django_db
def test_set_alert_notify_result_map_aggregates():
    from apps.alerts.models import NotifyResult

    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    NotifyResult.objects.create(notify_type="alert", notify_object="A1", notify_result=NotifyResultStatus.SUCCESS)
    NotifyResult.objects.create(notify_type="alert", notify_object="A1", notify_result=NotifyResultStatus.FAILED)
    result = AlertModelSerializer.set_alert_notify_result_map([alert])
    assert result["A1"] == [True, False]


def test_get_operator_user_empty():
    obj = SimpleNamespace(operator=[])
    assert _ser().get_operator_user(obj) == ""


def test_get_operator_user_with_map():
    obj = SimpleNamespace(operator=["u1", "u2"])
    ser = _ser(context={"operator_user_map": {"u1": "用户1", "u2": "用户2"}})
    assert ser.get_operator_user(obj) == "用户1, 用户2"


def test_get_notify_status_all_success():
    ser = _ser(notify_map={"A1": [True, True]})
    assert ser.get_notify_status(SimpleNamespace(alert_id="A1")) == NotifyResultStatus.SUCCESS


def test_get_notify_status_partial():
    ser = _ser(notify_map={"A1": [True, False]})
    assert ser.get_notify_status(SimpleNamespace(alert_id="A1")) == NotifyResultStatus.PARTIAL_SUCCESS


def test_get_notify_status_failed():
    ser = _ser(notify_map={"A1": [False]})
    assert ser.get_notify_status(SimpleNamespace(alert_id="A1")) == NotifyResultStatus.FAILED


def test_get_notify_status_empty():
    ser = _ser(notify_map={})
    assert ser.get_notify_status(SimpleNamespace(alert_id="X")) == ""


def test_get_duration_active():
    from apps.alerts.constants.constants import AlertStatus

    active = list(AlertStatus.ACTIVATE_STATUS)[0]
    obj = SimpleNamespace(created_at=timezone.now(), status=active)
    result = AlertModelSerializer.get_duration(obj)
    assert isinstance(result, str)


def test_get_incident_name_empty():
    obj = SimpleNamespace(incident_title_annotated=None)
    # 无注解且无 incident_set → 异常被吞，返回 ""
    obj.incident_set = SimpleNamespace(all=lambda: [])
    assert AlertModelSerializer.get_incident_name(obj) == ""


def test_get_event_count_annotated():
    obj = SimpleNamespace(event_count_annotated=7)
    assert AlertModelSerializer.get_event_count(obj) == 7


def test_get_source_names_annotated():
    obj = SimpleNamespace(source_names_annotated="Zabbix, Prometheus")
    assert AlertModelSerializer.get_source_names(obj) == "Zabbix, Prometheus"


def test_get_incident_name_annotated():
    obj = SimpleNamespace(incident_title_annotated="事故A")
    assert AlertModelSerializer.get_incident_name(obj) == "事故A"


def test_validate_team_superuser():
    request = SimpleNamespace(user=SimpleNamespace(is_superuser=True, group_list=[{"id": 1}]),
                             COOKIES={"current_team": "1"})
    ser = _ser(context={"request": request})
    assert ser.validate_team([1, 2]) == [1, 2]


def test_validate_team_no_request():
    ser = _ser(context={})
    assert ser.validate_team([1]) == [1]


@pytest.mark.django_db
def test_get_operator_user_db_fallback():
    from apps.system_mgmt.models.user import User

    User.objects.create(username="u1", display_name="用户1", domain="domain.com")
    obj = SimpleNamespace(operator=["u1"])
    ser = _ser(context={})
    assert "用户1" in ser.get_operator_user(obj)


@pytest.mark.django_db
def test_get_source_names_db_fallback():
    from django.utils import timezone

    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    src = AlertSource.objects.create(name="Zabbix", source_id="s1", source_type="zabbix", secret="x")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    ev = Event.objects.create(source=src, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1")
    alert.events.add(ev)
    # 无注解 → 走 events 关联查询
    assert AlertModelSerializer.get_source_names(alert) == "Zabbix"


@pytest.mark.django_db
def test_get_incident_name_db_fallback():
    from apps.alerts.models.models import Incident

    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    incident = Incident.objects.create(incident_id="I1", level="0", title="事故X", fingerprint="fp")
    incident.alert.add(alert)
    assert AlertModelSerializer.get_incident_name(alert) == "事故X"


@pytest.mark.django_db
def test_get_event_count_db_fallback():
    from django.utils import timezone

    from apps.alerts.models.alert_source import AlertSource
    from apps.alerts.models.models import Event

    src = AlertSource.objects.create(name="s", source_id="s1", source_type="restful", secret="x")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    ev = Event.objects.create(source=src, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1")
    alert.events.add(ev)
    # 无注解 → events.count()
    assert AlertModelSerializer.get_event_count(alert) == 1
