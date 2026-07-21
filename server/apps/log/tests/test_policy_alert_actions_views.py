"""Policy / Alert 视图层成功路径与定时任务逻辑测试。

补齐 enable / closed / last_event / stats / format_crontab 等未覆盖分支。
只 mock 权限边界（get_permissions_rules），DB 走真实。
"""
import pytest
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.web_utils import WebUtils
from apps.log.models.policy import (
    Alert,
    Event,
    EventRawData,
    Policy,
    PolicyOrganization,
)
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.log.views.policy import AlertViewSet, PolicyViewSet
from apps.system_mgmt.models.channel import Channel


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


def _create_policy(name, organization, collect_type=None, **overrides):
    data = {
        "name": name,
        "alert_type": "keyword",
        "alert_name": name,
        "alert_level": "warning",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "collect_type": collect_type,
    }
    data.update(overrides)
    policy = Policy.objects.create(**data)
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


def _invoke_alert_view(user, alert_id, method, action, data=None):
    factory = APIRequestFactory()
    request_factory = getattr(factory, method)
    request = request_factory(
        f"/api/v1/log/alert/{alert_id}/",
        data or {},
        format="json",
    )
    force_authenticate(request, user=user)
    view = AlertViewSet.as_view({method: action})
    return view(request, pk=alert_id)


def _allow_alert_view(mocker, policy_id):
    mocker.patch.object(
        AlertViewSet,
        "_get_all_accessible_policy_ids",
        return_value=[policy_id],
    )
    mocker.patch.object(AlertViewSet, "_authorize_alert_operate", return_value=None)


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


@pytest.mark.django_db
def test_patch_close_sends_closed_event_after_persisting_stable_time(authenticated_user, mocker):
    channel = Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
    )
    policy = _create_policy(
        "patch-close-nats",
        organization=1,
        notice=True,
        notice_type="nats",
        notice_type_id=channel.id,
    )
    alert = _create_alert(policy, "patch-close-nats-alert")
    _allow_alert_view(mocker, policy.id)
    notify_closed = mocker.patch.object(
        LogAlertLifecycleNotifier,
        "notify_closed",
        return_value=(True, {"result": True}),
    )
    mocker.patch(
        "apps.log.views.policy.transaction.on_commit",
        side_effect=lambda callback: callback(),
    )

    response = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "patch",
        "partial_update",
        {"status": "closed"},
    )

    assert response.status_code == status.HTTP_200_OK
    alert.refresh_from_db()
    assert alert.status == "closed"
    assert alert.operator == authenticated_user.username
    assert alert.end_event_time is not None
    assert alert.notice is True
    sent_alert = notify_closed.call_args.args[0]
    assert sent_alert.id == alert.id
    assert sent_alert.end_event_time == alert.end_event_time


@pytest.mark.django_db
def test_patch_close_failure_is_idempotent_and_keeps_pending_notice(authenticated_user, mocker):
    channel = Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
    )
    policy = _create_policy(
        "patch-close-fail",
        organization=1,
        notice=True,
        notice_type="nats",
        notice_type_id=channel.id,
    )
    alert = _create_alert(policy, "patch-close-fail-alert")
    _allow_alert_view(mocker, policy.id)
    notify_closed = mocker.patch.object(
        LogAlertLifecycleNotifier,
        "notify_closed",
        return_value=(False, {"result": False, "message": "down"}),
    )
    mocker.patch(
        "apps.log.views.policy.transaction.on_commit",
        side_effect=lambda callback: callback(),
    )

    first = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "patch",
        "partial_update",
        {"status": "closed"},
    )
    alert.refresh_from_db()
    closed_at = alert.end_event_time
    second = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "patch",
        "partial_update",
        {"status": "closed"},
    )

    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    alert.refresh_from_db()
    assert alert.end_event_time == closed_at
    assert alert.notice is False
    notify_closed.assert_called_once()


@pytest.mark.django_db
def test_patch_close_on_normal_channel_preserves_notice_state(authenticated_user, mocker):
    channel = Channel.objects.create(name="邮件", channel_type="email", config={}, description="")
    policy = _create_policy(
        "patch-close-mail",
        organization=1,
        notice=True,
        notice_type="email",
        notice_type_id=channel.id,
        notice_users=["admin"],
    )
    alert = _create_alert(policy, "patch-close-mail-alert")
    alert.notice = True
    alert.save(update_fields=["notice"])
    _allow_alert_view(mocker, policy.id)
    notify_closed = mocker.patch.object(LogAlertLifecycleNotifier, "notify_closed")

    response = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "patch",
        "partial_update",
        {"status": "closed"},
    )

    assert response.status_code == status.HTTP_200_OK
    alert.refresh_from_db()
    assert alert.status == "closed"
    assert alert.notice is True
    notify_closed.assert_not_called()


@pytest.mark.django_db
def test_legacy_closed_action_reuses_alert_lifecycle(authenticated_user, mocker):
    channel = Channel.objects.create(
        name="告警中心旧入口",
        channel_type="nats",
        config={"method_name": "receive_alert_events"},
        description="",
    )
    policy = _create_policy(
        "legacy-close-nats",
        organization=1,
        notice=True,
        notice_type="nats",
        notice_type_id=channel.id,
    )
    alert = _create_alert(policy, "legacy-close-nats-alert")
    _allow_alert_view(mocker, policy.id)
    notify_closed = mocker.patch.object(
        LogAlertLifecycleNotifier,
        "notify_closed",
        return_value=(True, {"result": True}),
    )
    mocker.patch(
        "apps.log.views.policy.transaction.on_commit",
        side_effect=lambda callback: callback(),
    )

    response = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "post",
        "closed",
    )

    assert response.status_code == status.HTTP_200_OK
    alert.refresh_from_db()
    assert alert.status == "closed"
    assert alert.end_event_time is not None
    assert alert.notice is True
    notify_closed.assert_called_once()


@pytest.mark.django_db
def test_patch_close_denied_by_operate_permission(authenticated_user, mocker):
    policy = _create_policy("patch-close-denied", organization=1)
    alert = _create_alert(policy, "patch-close-denied-alert")
    mocker.patch.object(
        AlertViewSet,
        "_get_all_accessible_policy_ids",
        return_value=[policy.id],
    )
    mocker.patch.object(
        AlertViewSet,
        "_authorize_alert_operate",
        return_value=WebUtils.response_403("denied"),
    )

    response = _invoke_alert_view(
        authenticated_user,
        alert.id,
        "patch",
        "partial_update",
        {"status": "closed"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    alert.refresh_from_db()
    assert alert.status == "new"


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
