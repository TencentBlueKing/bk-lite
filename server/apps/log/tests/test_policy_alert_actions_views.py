"""Policy / Alert 视图层成功路径与定时任务逻辑测试。

补齐 enable / closed / last_event / stats / format_crontab 等未覆盖分支。
只 mock 权限边界（get_permissions_rules），DB 走真实。
"""
import pytest
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import status

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.log.models.policy import (
    Alert,
    Event,
    EventRawData,
    Policy,
    PolicyOrganization,
)
from apps.log.views.policy import PolicyViewSet


def _mock_policy_permission(mocker, policy_id=None, organization=1):
    instance_permissions = []
    if policy_id is not None:
        instance_permissions.append({"id": policy_id, "permission": ["View", "Operate"]})
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={
            "data": {"None": {"instance": instance_permissions}},
            "team": [organization],
        },
    )


def _create_policy(name, organization, collect_type=None):
    policy = Policy.objects.create(
        name=name,
        alert_type="keyword",
        alert_name=name,
        alert_level="warning",
        alert_condition={"query": "error"},
        schedule={"type": "min", "value": 5},
        period={"type": "min", "value": 5},
        collect_type=collect_type,
    )
    PolicyOrganization.objects.create(policy=policy, organization=organization)
    return policy


def _create_alert(policy, alert_id, status_value="new"):
    return Alert.objects.create(
        id=alert_id,
        policy=policy,
        source_id=f"source-{alert_id}",
        level="warning",
        content="alert content",
        status=status_value,
        start_event_time=timezone.now(),
    )


# --------------------------- format_crontab (纯逻辑) ---------------------------


@pytest.mark.django_db
def test_format_crontab_minute_creates_schedule():
    viewset = PolicyViewSet()
    cron = viewset.format_crontab({"type": "min", "value": 5})
    assert isinstance(cron, CrontabSchedule)
    assert cron.minute == "*/5"
    assert cron.hour == "*"


@pytest.mark.django_db
def test_format_crontab_hour_creates_schedule():
    viewset = PolicyViewSet()
    cron = viewset.format_crontab({"type": "hour", "value": 2})
    assert cron.hour == "*/2"
    assert cron.minute == 0


@pytest.mark.django_db
def test_format_crontab_day_creates_schedule():
    viewset = PolicyViewSet()
    cron = viewset.format_crontab({"type": "day", "value": 3})
    assert cron.day_of_month == "*/3"
    assert cron.hour == 0


@pytest.mark.django_db
def test_format_crontab_invalid_type_raises():
    viewset = PolicyViewSet()
    with pytest.raises(BaseAppException):
        viewset.format_crontab({"type": "week", "value": 1})


@pytest.mark.django_db
def test_update_or_create_task_replaces_existing_task():
    viewset = PolicyViewSet()
    # 预置一个同名旧任务，确认会被删除并重建
    old_cron = CrontabSchedule.objects.create(minute="*/1")
    PeriodicTask.objects.create(name="log_policy_task_p1", task="x", crontab=old_cron)

    viewset.update_or_create_task("p1", {"type": "min", "value": 10})

    tasks = PeriodicTask.objects.filter(name="log_policy_task_p1")
    assert tasks.count() == 1
    task = tasks.first()
    assert task.task == "apps.log.tasks.policy.scan_log_policy_task"
    assert task.enabled is True
    assert task.crontab.minute == "*/10"


# --------------------------- enable action ---------------------------


@pytest.mark.django_db
def test_enable_toggles_task_and_sets_last_run_time(api_client, authenticated_user, mocker):
    policy = _create_policy("enable-policy", organization=1)
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)
    cron = CrontabSchedule.objects.create(minute="*/5")
    PeriodicTask.objects.create(name=f"log_policy_task_{policy.id}", task="x", crontab=cron, enabled=False)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(f"/api/v1/log/policy/{policy.id}/enable/", data={"enabled": True}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["enabled"] is True
    task = PeriodicTask.objects.get(name=f"log_policy_task_{policy.id}")
    assert task.enabled is True
    # 从禁用->启用，应回填 last_run_time
    policy.refresh_from_db()
    assert policy.last_run_time is not None


@pytest.mark.django_db
def test_enable_disable_does_not_set_last_run_time(api_client, authenticated_user, mocker):
    policy = _create_policy("disable-policy", organization=1)
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)
    cron = CrontabSchedule.objects.create(minute="*/5")
    PeriodicTask.objects.create(name=f"log_policy_task_{policy.id}", task="x", crontab=cron, enabled=True)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(f"/api/v1/log/policy/{policy.id}/enable/", data={"enabled": False}, format="json")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["data"]["enabled"] is False
    task = PeriodicTask.objects.get(name=f"log_policy_task_{policy.id}")
    assert task.enabled is False
    policy.refresh_from_db()
    assert policy.last_run_time is None


@pytest.mark.django_db
def test_enable_returns_error_when_task_missing(api_client, authenticated_user, mocker):
    policy = _create_policy("notask-policy", organization=1)
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(f"/api/v1/log/policy/{policy.id}/enable/", data={"enabled": True}, format="json")

    # response_error 首位参数是 data，message 为空，状态 400
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["result"] is False
    assert "定时任务不存在" in response.json()["data"]


# --------------------------- alert closed (成功路径) ---------------------------


@pytest.mark.django_db
def test_alert_closed_success_updates_status_and_operator(api_client, authenticated_user, mocker):
    policy = _create_policy("closed-ok-policy", organization=1)
    alert = _create_alert(policy, "alert-close-ok")
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.post(f"/api/v1/log/alert/{alert.id}/closed/")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()["data"]
    assert body["operator"] == authenticated_user.username
    alert.refresh_from_db()
    assert alert.status == body["status"]
    assert alert.operator == authenticated_user.username


# --------------------------- last_event ---------------------------


@pytest.mark.django_db
def test_last_event_missing_alert_id_returns_error(api_client, authenticated_user, mocker):
    _mock_policy_permission(mocker, organization=1)
    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/alert/last_event/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["result"] is False
    assert "缺少告警ID" in response.json()["data"]


@pytest.mark.django_db
def test_last_event_success_returns_event_and_raw_data(api_client, authenticated_user, mocker):
    policy = _create_policy("last-event-ok", organization=1)
    alert = _create_alert(policy, "alert-le-ok")
    event = Event.objects.create(
        id="event-le-ok",
        policy=policy,
        alert=alert,
        source_id=alert.source_id,
        event_time=timezone.now(),
        level="warning",
        content="event content",
    )
    EventRawData.objects.create(event=event, data={"message": "raw"})
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/last_event/?alert_id={alert.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["event"]["id"] == event.id
    assert data["raw_data"]["data"]["message"] == "raw"


@pytest.mark.django_db
def test_last_event_no_event_returns_404(api_client, authenticated_user, mocker):
    policy = _create_policy("last-event-noevent", organization=1)
    alert = _create_alert(policy, "alert-le-noevent")
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get(f"/api/v1/log/alert/last_event/?alert_id={alert.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "未找到相关事件" in response.json()["data"]


# --------------------------- stats ---------------------------


@pytest.mark.django_db
def test_stats_empty_when_no_accessible_policies(api_client, authenticated_user, mocker):
    # 无任何策略权限 -> policy_ids 为空，返回空统计骨架
    _mock_policy_permission(mocker, organization=1)
    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/alert/stats/?step=30")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["total"] == 0
    assert data["step_minutes"] == 30
    assert data["time_series"] == []


@pytest.mark.django_db
def test_stats_counts_alerts_in_time_series(api_client, authenticated_user, mocker):
    policy = _create_policy("stats-policy", organization=1)
    _create_alert(policy, "alert-stat-1", status_value="new")
    _create_alert(policy, "alert-stat-2", status_value="new")
    _mock_policy_permission(mocker, policy_id=policy.id, organization=1)

    api_client.cookies["current_team"] = "1"
    response = api_client.get("/api/v1/log/alert/stats/?status=new&step=60")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["status"] == "new"
    assert data["step_minutes"] == 60
    # 有数据时 time_range 应被填充
    assert data["time_range"]["start"] is not None
