"""日志策略 / 告警 handlers 序列化。"""

import json
import logging

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.log.models.policy import Alert, Event, Policy, PolicyOrganization
from apps.log.serializers.policy import PolicySerializer
from apps.log.views.policy import AlertViewSet
from apps.system_mgmt.models import Channel, Group, User

pytestmark = pytest.mark.django_db


def _policy(**overrides):
    values = {
        "name": "handler-policy",
        "alert_type": "keyword",
        "alert_name": "handler-policy",
        "alert_level": "warning",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "notice": False,
    }
    values.update(overrides)
    policy = Policy.objects.create(**values)
    PolicyOrganization.objects.create(policy=policy, organization=1)
    return policy


def _request(user, path="/api/v1/log/alert/"):
    request = APIRequestFactory().get(path)
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def grant_all(authenticated_user, mocker):
    authenticated_user.is_superuser = True
    authenticated_user.save(update_fields=["is_superuser"])
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )
    mocker.patch(
        "apps.log.views.policy.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    return authenticated_user


def test_policy_serializer_exposes_and_persists_handlers():
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
        group_list=[1],
    )
    policy = _policy()
    serializer = PolicySerializer(policy, data={"handlers": [user.id]}, partial=True)

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    policy.refresh_from_db()

    assert policy.handlers == [user.id]
    assert PolicySerializer(policy).data["handlers"] == [user.id]


def test_policy_serializer_defaults_handlers_to_empty_list():
    policy = _policy()

    assert policy.handlers == []
    assert PolicySerializer(policy).data["handlers"] == []


def test_policy_save_rejects_handlers_outside_policy_organizations():
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    disabled = _org_user(username="disabled1", disabled=True)
    policy = _policy()

    ok = PolicySerializer(policy, data={"handlers": [inside.id]}, partial=True)
    assert ok.is_valid(), ok.errors
    ok.save()
    policy.refresh_from_db()
    assert policy.handlers == [inside.id]

    outside = PolicySerializer(policy, data={"handlers": [outsider.id]}, partial=True)
    disabled_ser = PolicySerializer(policy, data={"handlers": [disabled.id]}, partial=True)
    missing = PolicySerializer(policy, data={"handlers": [999999]}, partial=True)
    org_change = PolicySerializer(
        policy,
        data={"alert_name": policy.alert_name},
        partial=True,
        context={"policy_organizations": [2]},
    )

    assert not outside.is_valid()
    assert "handlers" in outside.errors
    assert not disabled_ser.is_valid()
    assert "handlers" in disabled_ser.errors
    assert not missing.is_valid()
    assert "handlers" in missing.errors
    assert not org_change.is_valid()
    assert "handlers" in org_change.errors
    policy.refresh_from_db()
    assert policy.handlers == [inside.id]


def test_policy_create_rejects_handlers_outside_organizations(api_client, grant_all, mocker):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    mocker.patch("apps.log.views.policy.PolicyViewSet.update_or_create_task")
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    api_client.cookies["current_team"] = "1"
    payload = {
        "name": "handler-org-policy",
        "alert_type": "keyword",
        "alert_name": "handler-org-policy",
        "alert_level": "warning",
        "alert_condition": {"query": "error"},
        "schedule": {"type": "min", "value": 5},
        "period": {"type": "min", "value": 5},
        "organizations": [1],
    }

    ok = api_client.post("/api/v1/log/policy/", {**payload, "handlers": [inside.id]}, format="json")
    outside = api_client.post(
        "/api/v1/log/policy/",
        {
            **payload,
            "name": "handler-org-policy-out",
            "alert_name": "handler-org-policy-out",
            "handlers": [outsider.id],
        },
        format="json",
    )

    assert ok.status_code == 201
    assert ok.json()["data"]["handlers"] == [inside.id]
    assert outside.status_code == 400
    assert "handlers" in str(outside.json())


def test_alert_list_exposes_handlers_and_display(grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    Alert.objects.create(
        id="handler-alert-1",
        policy=policy,
        source_id="src-1",
        level="warning",
        status="new",
        start_event_time=timezone.now(),
        organizations=[1],
        handlers=[user.id],
    )

    listed = AlertViewSet.as_view({"get": "list"})(_request(grant_all))

    assert listed.status_code == 200
    item = json.loads(listed.content)["data"]["items"][0]
    assert item["handlers"] == [user.id]
    assert item["handlers_display"] == ["处理人甲(handler1)"]


def test_my_alert_filters_handlers_not_operator(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    other = _org_user()
    policy = _policy()
    mine = _new_alert(policy, "mine", handlers=[actor.id])
    operator_only = _new_alert(policy, "operator-only", handlers=[], operator="testuser")
    others = _new_alert(policy, "other", handlers=[other.id])
    _new_alert(policy, "hidden", handlers=[actor.id], organizations=[99])
    api_client.cookies["current_team"] = "1"

    listed = api_client.get("/api/v1/log/alert/", {"page": 1, "page_size": 20})
    mine_listed = api_client.get("/api/v1/log/alert/", {"page": 1, "page_size": 20, "my_alert": "1"})
    listed_all = api_client.get("/api/v1/log/alert/all/", {"page": 1, "page_size": 20})
    mine_all = api_client.get("/api/v1/log/alert/all/", {"page": 1, "page_size": 20, "my_alert": "1"})
    listed_stats = api_client.get("/api/v1/log/alert/stats/", {"status": "new", "step": 60})
    mine_stats = api_client.get("/api/v1/log/alert/stats/", {"status": "new", "step": 60, "my_alert": "1"})

    listed_ids = {item["id"] for item in listed.json()["data"]["items"]}
    mine_ids = {item["id"] for item in mine_listed.json()["data"]["items"]}
    listed_all_ids = {item["id"] for item in listed_all.json()["data"]["items"]}
    mine_all_ids = {item["id"] for item in mine_all.json()["data"]["items"]}
    assert listed.status_code == 200
    assert mine_listed.status_code == 200
    assert listed_all.status_code == 200
    assert mine_all.status_code == 200
    assert listed_stats.status_code == 200
    assert mine_stats.status_code == 200
    assert listed_ids == {mine.id, operator_only.id, others.id}
    assert mine_ids == {mine.id}
    assert listed_all_ids == listed_ids
    assert mine_all_ids == {mine.id}
    assert listed_stats.json()["data"]["total"] == 3
    assert mine_stats.json()["data"]["total"] == 1


def _actor_user():
    return User.objects.create(
        username="testuser",
        display_name="测试用户",
        email="testuser@example.com",
        password="x",
        group_list=[1],
    )


def _org_user(*, username="assignee1", organization=1, disabled=False):
    return User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        disabled=disabled,
        group_list=[organization],
    )


def _new_alert(policy, alert_id, **kwargs):
    kwargs.setdefault("organizations", [1])
    kwargs.setdefault("handlers", [])
    kwargs.setdefault("status", "new")
    return Alert.objects.create(
        id=alert_id,
        policy=policy,
        source_id=f"source-{alert_id}",
        level="warning",
        start_event_time=timezone.now(),
        **kwargs,
    )


def test_claim_empty_active_alert_then_second_claim_conflicts(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    policy = _policy()
    alert = _new_alert(policy, "claim-1")
    api_client.cookies["current_team"] = "1"

    first = api_client.post(f"/api/v1/log/alert/{alert.id}/claim/")
    second = api_client.post(f"/api/v1/log/alert/{alert.id}/claim/")

    assert first.status_code == 200
    assert first.json()["data"]["handlers"] == [actor.id]
    assert first.json()["data"]["handlers_display"] == ["测试用户(testuser)"]
    alert.refresh_from_db()
    assert alert.handlers == [actor.id]
    assert alert.operator in (None, "")
    assert second.status_code == 409
    claimed = list(Event.objects.filter(alert=alert, action=Event.Action.CLAIMED))
    assert len(claimed) == 1
    assert actor.username in claimed[0].content
    assert alert.status == "new"


def test_assign_org_user_succeeds_and_rejects_outsiders(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    notify = mocker.patch("apps.log.services.alert_lifecycle_notify.LogAlertLifecycleNotifier.notify_assigned")
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    disabled = _org_user(username="disabled1", disabled=True)
    policy = _policy(notice=True)
    alert = _new_alert(policy, "assign-ok")
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        ok = api_client.post(
            f"/api/v1/log/alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )
    alert.refresh_from_db()
    assert ok.status_code == 200
    assert alert.handlers == [inside.id]
    notify.assert_called_once()
    assigned = list(Event.objects.filter(alert=alert, action=Event.Action.ASSIGNED))
    assert len(assigned) == 1
    assert inside.username in assigned[0].content

    taken = api_client.post(
        f"/api/v1/log/alert/{alert.id}/assign/",
        {"handlers": [inside.id]},
        format="json",
    )
    assert taken.status_code == 409

    empty = _new_alert(policy, "assign-empty")
    outside = api_client.post(
        f"/api/v1/log/alert/{empty.id}/assign/",
        {"handlers": [outsider.id]},
        format="json",
    )
    disabled_resp = api_client.post(
        f"/api/v1/log/alert/{empty.id}/assign/",
        {"handlers": [disabled.id]},
        format="json",
    )
    empty.refresh_from_db()
    assert outside.status_code == 400
    assert disabled_resp.status_code == 400
    missing = api_client.post(
        f"/api/v1/log/alert/{empty.id}/assign/",
        {"handlers": [999999]},
        format="json",
    )
    empty.refresh_from_db()
    assert missing.status_code == 400
    assert empty.handlers == []


def test_handlers_present_blocks_claim_assign_but_close_still_works(api_client, grant_all, mocker):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    mocker.patch("apps.log.views.policy.LogAlertLifecycleNotifier")
    owner = _org_user()
    policy = _policy()
    alert = _new_alert(policy, "owned-1", handlers=[owner.id])
    api_client.cookies["current_team"] = "1"

    claimed = api_client.post(f"/api/v1/log/alert/{alert.id}/claim/")
    assigned = api_client.post(
        f"/api/v1/log/alert/{alert.id}/assign/",
        {"handlers": [owner.id]},
        format="json",
    )
    closed = api_client.post(f"/api/v1/log/alert/{alert.id}/closed/")

    alert.refresh_from_db()
    assert claimed.status_code == 409
    assert assigned.status_code == 409
    assert closed.status_code == 200
    assert alert.status == "closed"
    assert alert.handlers == [owner.id]
    assert Event.objects.filter(alert=alert, action=Event.Action.CLAIMED).count() == 0
    assert Event.objects.filter(alert=alert, action=Event.Action.ASSIGNED).count() == 0
    closed_events = list(Event.objects.filter(alert=alert, action=Event.Action.CLOSED))
    assert len(closed_events) == 1
    assert "testuser" in closed_events[0].content


def test_inactive_alert_cannot_claim_or_assign(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    owner = _org_user()
    policy = _policy()
    closed = _new_alert(policy, "closed-1", status="closed")
    api_client.cookies["current_team"] = "1"

    claim = api_client.post(f"/api/v1/log/alert/{closed.id}/claim/")
    assign = api_client.post(
        f"/api/v1/log/alert/{closed.id}/assign/",
        {"handlers": [owner.id]},
        format="json",
    )
    closed.refresh_from_db()
    assert claim.status_code == 409
    assert assign.status_code == 409
    assert closed.handlers == []


def test_deleted_policy_allows_claim_and_skips_assign_notify(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    notify = mocker.patch("apps.log.services.alert_lifecycle_notify.LogAlertLifecycleNotifier.notify_assigned")
    assignee = _org_user()
    policy = _policy(notice=True)
    claim_alert = _new_alert(policy, "claim-orphan")
    assign_alert = _new_alert(policy, "assign-orphan")
    policy.delete()
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        claimed = api_client.post(f"/api/v1/log/alert/{claim_alert.id}/claim/")
        assigned = api_client.post(
            f"/api/v1/log/alert/{assign_alert.id}/assign/",
            {"handlers": [assignee.id]},
            format="json",
        )

    claim_alert.refresh_from_db()
    assign_alert.refresh_from_db()
    assert claimed.status_code == 200
    assert claim_alert.handlers == [actor.id]
    assert assigned.status_code == 200
    assert assign_alert.handlers == [assignee.id]
    notify.assert_not_called()


def test_claim_does_not_send_assign_notify(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    _actor_user()
    notify = mocker.patch("apps.log.services.alert_lifecycle_notify.LogAlertLifecycleNotifier.notify_assigned")
    policy = _policy(notice=True)
    alert = _new_alert(policy, "claim-no-notify")
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(f"/api/v1/log/alert/{alert.id}/claim/")

    assert resp.status_code == 200
    notify.assert_not_called()


def _person_channel():
    return Channel.objects.create(
        name="邮件",
        channel_type="email",
        config={},
        description="",
        team=[1],
    )


def _alert_center_channel():
    return Channel.objects.create(
        name="告警中心",
        channel_type="nats",
        config={"method_name": "receive_alert_events", "namespace": "default"},
        description="",
        team=[1],
    )


def test_assign_sends_notice_to_handlers_not_notice_users(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _person_channel()
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(
        notice=True,
        notice_type="email",
        notice_type_id=channel.id,
        notice_users=["policy-notice-user"],
    )
    alert = _new_alert(policy, "assign-notice")
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"/api/v1/log/alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert resp.status_code == 200
    send.assert_called_once()
    channel_id, title, _content, receivers = send.call_args.args
    assert channel_id == channel.id
    assert "分派" in title
    assert receivers == [str(inside.id)]
    assert "policy-notice-user" not in receivers


def test_assign_notice_skips_alert_center_channel(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _alert_center_channel()
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(notice=True, notice_type="nats", notice_type_id=channel.id)
    alert = _new_alert(policy, "assign-nats")
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"/api/v1/log/alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert resp.status_code == 200
    send.assert_not_called()


def test_assign_notice_off_does_not_send(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    send = mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(notice=False, notice_type_id=_person_channel().id, notice_users=["u1"])
    alert = _new_alert(policy, "assign-silent")
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"/api/v1/log/alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert resp.status_code == 200
    send.assert_not_called()


def test_claim_requires_operate_permission(api_client, grant_all, mocker):
    from apps.core.utils.web_utils import WebUtils

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    _actor_user()
    policy = _policy()
    alert = _new_alert(policy, "claim-denied")
    mocker.patch(
        "apps.log.views.policy.AlertViewSet._authorize_alert_operate",
        return_value=WebUtils.response_403("User does not have permission to operate this alert"),
    )
    api_client.cookies["current_team"] = "1"

    resp = api_client.post(f"/api/v1/log/alert/{alert.id}/claim/")

    assert resp.status_code == 403
    alert.refresh_from_db()
    assert alert.handlers == []


def test_claim_logs_lifecycle_template_without_handler_payload(grant_all, caplog):
    from apps.log.services.alert_handlers import claim_alert as claim_alert_service

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    policy = _policy()
    alert = _new_alert(policy, "claim-log")
    caplog.set_level(logging.INFO, logger="log")

    claimed = claim_alert_service(alert, actor=actor)

    records = [record for record in caplog.records if record.msg == "event=alert_claimed alert_id=%s"]
    assert claimed.handlers == [actor.id]
    assert len(records) == 1
    assert records[0].args == (alert.pk,)
    rendered = records[0].getMessage()
    assert str(alert.pk) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered


def test_assign_notice_logs_without_handler_payload(grant_all, caplog, mocker):
    from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _person_channel()
    mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(notice=True, notice_type_id=channel.id)
    alert = _new_alert(policy, "assign-log", handlers=[inside.id])
    caplog.set_level(logging.INFO, logger="log")

    ok, _ = LogAlertLifecycleNotifier(policy).notify_assigned(alert, max_attempts=1)

    records = [
        record
        for record in caplog.records
        if record.msg == "event=assign_notify_sent policy_id=%s alert_id=%s attempt=%s"
    ]
    assert ok is True
    assert len(records) == 1
    assert records[0].args == (policy.id, alert.id, 1)
    rendered = records[0].getMessage()
    assert str(alert.id) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered


def test_assign_logs_lifecycle_template_without_handler_payload(grant_all, caplog):
    from apps.log.services.alert_handlers import assign_alert as assign_alert_service

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    inside = _org_user()
    policy = _policy()
    alert = _new_alert(policy, "assign-log-event")
    caplog.set_level(logging.INFO, logger="log")

    assigned = assign_alert_service(alert, handlers=[inside.id], actor=actor)

    records = [
        record
        for record in caplog.records
        if record.msg == "event=alert_assigned alert_id=%s handler_count=%s"
    ]
    assert assigned.handlers == [inside.id]
    assert len(records) == 1
    assert records[0].args == (alert.pk, 1)
    rendered = records[0].getMessage()
    assert str(alert.pk) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered


def test_assign_notify_failed_omits_traceback_and_channel_payload(grant_all, caplog, mocker):
    from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _person_channel()
    mocker.patch(
        "apps.log.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        side_effect=RuntimeError("smtp-password=secret"),
    )
    inside = _org_user()
    policy = _policy(notice=True, notice_type_id=channel.id)
    alert = _new_alert(policy, "assign-fail", handlers=[inside.id])
    caplog.set_level(logging.ERROR, logger="log")

    ok, result = LogAlertLifecycleNotifier(policy).notify_assigned(alert, max_attempts=1)

    records = [
        record
        for record in caplog.records
        if record.msg
        == "event=assign_notify_failed policy_id=%s alert_id=%s attempt=%s failed_stage=send error_type=%s"
    ]
    assert ok is False
    assert result == {"result": False, "message": "RuntimeError"}
    assert len(records) == 1
    assert records[0].name == "log"
    assert records[0].args == (policy.id, alert.id, 1, "RuntimeError")
    assert records[0].exc_info is None
    rendered = records[0].getMessage()
    assert "smtp-password=secret" not in rendered
    assert "password" not in rendered.lower()
