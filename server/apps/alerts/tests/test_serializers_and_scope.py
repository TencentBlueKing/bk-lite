"""告警/事故/告警源序列化器与 operator_scope 覆盖测试。

对照 spec/prd/告警中心：告警/事故展示持续时间、来源、处理人，处理人受组织范围约束。
"""

from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework import serializers as drf_serializers

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Incident
from apps.alerts.serializers.alert import AlertModelSerializer
from apps.alerts.serializers.alert_source import AlertSourceModelSerializer
from apps.alerts.serializers.incident import IncidentModelSerializer
from apps.alerts.utils import operator_scope as os_mod


# --------------------------------------------------------------------------
# operator_scope
# --------------------------------------------------------------------------


def test_normalize_usernames_dedup_and_strip():
    assert os_mod.normalize_usernames([" a ", "a", "b", ""]) == ["a", "b"]


def test_normalize_usernames_string_input():
    assert os_mod.normalize_usernames("alice") == ["alice"]


def test_normalize_usernames_empty():
    assert os_mod.normalize_usernames(None) == []
    assert os_mod.normalize_usernames(123) == []


def test_normalize_group_ids_mixed():
    assert os_mod.normalize_group_ids([{"id": 1}, 2, "3", {"id": "x"}, None]) == {1, 2, 3}


@pytest.mark.django_db
def test_validate_usernames_in_groups_missing_user():
    names, msg = os_mod.validate_usernames_in_groups(["ghost"], {1}, "测试")
    assert "不存在" in msg


@pytest.mark.django_db
def test_validate_usernames_in_groups_out_of_scope():
    from apps.system_mgmt.models.user import User

    User.objects.create(username="bob", domain="domain.com", group_list=[{"id": 9}])
    names, msg = os_mod.validate_usernames_in_groups(["bob"], {1}, "测试")
    assert "范围内" in msg


@pytest.mark.django_db
def test_validate_usernames_in_groups_ok():
    from apps.system_mgmt.models.user import User

    User.objects.create(username="carol", domain="domain.com", group_list=[{"id": 1}])
    names, msg = os_mod.validate_usernames_in_groups(["carol"], {1}, "测试")
    assert msg is None
    assert names == ["carol"]


@pytest.mark.django_db
def test_validate_incident_operators_aggregates_alert_teams():
    from apps.system_mgmt.models.user import User

    User.objects.create(username="dan", domain="domain.com", group_list=[{"id": 2}])
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[2])
    names, msg = os_mod.validate_incident_operators([alert], ["dan"])
    assert msg is None


# --------------------------------------------------------------------------
# AlertModelSerializer 静态方法
# --------------------------------------------------------------------------


def test_alert_get_duration_inactive_status():
    obj = SimpleNamespace(created_at=timezone.now(), status="closed")
    assert AlertModelSerializer.get_duration(obj) == "--"


@pytest.mark.django_db
def test_alert_get_duration_active():
    from apps.alerts.constants.constants import AlertStatus

    active_status = list(AlertStatus.ACTIVATE_STATUS)[0]
    obj = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", status=active_status)
    result = AlertModelSerializer.get_duration(obj)
    assert result.endswith("s") or "m" in result


@pytest.mark.django_db
def test_alert_get_event_count_and_source_names():
    source = AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")
    alert = Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp")
    event = Event.objects.create(
        source=source, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1"
    )
    alert.events.add(event)
    assert AlertModelSerializer.get_event_count(alert) == 1
    assert "源1" in AlertModelSerializer.get_source_names(alert)


def test_alert_get_notify_status_variants():
    ser = AlertModelSerializer.__new__(AlertModelSerializer)
    ser.alert_notify_result_map = {"A1": [True, True], "A2": [True, False], "A3": [False, False]}
    from apps.alerts.constants.constants import NotifyResultStatus

    assert ser.get_notify_status(SimpleNamespace(alert_id="A1")) == NotifyResultStatus.SUCCESS
    assert ser.get_notify_status(SimpleNamespace(alert_id="A2")) == NotifyResultStatus.PARTIAL_SUCCESS
    assert ser.get_notify_status(SimpleNamespace(alert_id="A3")) == NotifyResultStatus.FAILED
    assert ser.get_notify_status(SimpleNamespace(alert_id="missing")) == ""


# --------------------------------------------------------------------------
# IncidentModelSerializer.get_duration
# --------------------------------------------------------------------------


def test_incident_get_duration_inactive():
    obj = SimpleNamespace(status="closed", created_at=timezone.now())
    assert IncidentModelSerializer.get_duration(obj) == "--"


@pytest.mark.django_db
def test_incident_get_duration_active():
    from apps.alerts.constants.constants import IncidentStatus

    active = list(IncidentStatus.ACTIVATE_STATUS)[0]
    inc = Incident.objects.create(incident_id="I1", level="0", title="t", fingerprint="fp", status=active)
    result = IncidentModelSerializer.get_duration(inc)
    assert isinstance(result, str)
    assert result != "--"


# --------------------------------------------------------------------------
# AlertSourceModelSerializer
# --------------------------------------------------------------------------


def test_alert_source_deep_merge_config():
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 10}, "e": 5}
    merged = AlertSourceModelSerializer._deep_merge_config(base, override)
    assert merged == {"a": {"b": 10, "c": 2}, "d": 3, "e": 5}


def test_alert_source_build_default_config_default_type():
    cfg = AlertSourceModelSerializer._build_default_config("restful", "s1")
    assert isinstance(cfg, dict)


def test_alert_source_validate_merges_config():
    ser = AlertSourceModelSerializer.__new__(AlertSourceModelSerializer)
    ser.instance = None
    attrs = {"source_type": "restful", "source_id": "s1", "config": {"custom": 1}}
    out = ser.validate(attrs)
    assert out["config"]["custom"] == 1


@pytest.mark.django_db
def test_alert_source_get_event_count_and_last_event_time():
    source = AlertSource.objects.create(name="源1", source_id="s1", source_type="restful", secret="x")
    Event.objects.create(source=source, raw_data={}, title="e", level="0", start_time=timezone.now(), event_id="E1")
    assert AlertSourceModelSerializer.get_event_count(source) == 1
    assert AlertSourceModelSerializer.get_last_event_time(source) != ""


@pytest.mark.django_db
def test_alert_source_get_last_event_time_empty():
    source = AlertSource.objects.create(name="源2", source_id="s2", source_type="restful", secret="x")
    assert AlertSourceModelSerializer.get_last_event_time(source) == ""


@pytest.mark.django_db
def test_alert_source_serializer_team_secrets_write_only():
    """team_secrets 必须为 write_only，GET 响应不得返回组织密钥。

    验证点：revert write_only 后此测试失败（字段出现在 data 中）。
    """
    source = AlertSource.objects.create(
        name="源3",
        source_id="s3",
        source_type="restful",
        secret="base-secret",
        team_secrets={1: "team-secret-abc"},
    )
    ser = AlertSourceModelSerializer(source)
    data = ser.data
    # team_secrets 不得出现在序列化输出中（write_only=True）
    assert "team_secrets" not in data, (
        "team_secrets 以明文出现在 GET 响应中，存在组织密钥泄露风险"
    )
    # secret 同理
    assert "secret" not in data, "secret 以明文出现在 GET 响应中"
