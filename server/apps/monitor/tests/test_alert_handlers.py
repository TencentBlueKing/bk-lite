"""监控策略 / 告警 handlers 序列化。"""

import logging

import pytest

from apps.monitor.models import MonitorAlert, MonitorEvent
from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.system_mgmt.models import Channel, Group, User

pytestmark = pytest.mark.django_db

BASE = "/api/v1/monitor"


@pytest.fixture
def grant_all(mocker):
    mocker.patch(
        "apps.monitor.views.monitor_alert.get_permissions_rules",
        return_value={"data": {"all": {"team": [1]}}, "team": [1]},
    )
    mocker.patch(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        return_value={"result": True, "data": [1]},
    )


def _policy(**overrides):
    obj = MonitorObject.objects.create(name="HandlerPolicyObj", level="base")
    values = {
        "monitor_object": obj,
        "name": "handler-policy",
        "algorithm": "max",
        "query_condition": {},
        "source": {},
        "group_by": [],
    }
    values.update(overrides)
    policy = MonitorPolicy.objects.create(organizations=[1], **values)
    PolicyOrganization.objects.create(policy=policy, organization=1)
    return policy


def test_policy_serializer_exposes_and_persists_handlers():
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
        group_list=[1],
    )
    policy = _policy()
    serializer = MonitorPolicySerializer(
        policy,
        data={"handlers": [user.id]},
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    serializer.save()
    policy.refresh_from_db()

    assert policy.handlers == [user.id]
    assert MonitorPolicySerializer(policy).data["handlers"] == [user.id]


def test_policy_serializer_defaults_handlers_to_empty_list():
    policy = _policy()

    assert policy.handlers == []
    assert MonitorPolicySerializer(policy).data["handlers"] == []


def test_policy_save_rejects_handlers_outside_policy_organizations():
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    disabled = _org_user(username="disabled1", disabled=True)
    policy = _policy()

    ok = MonitorPolicySerializer(policy, data={"handlers": [inside.id]}, partial=True)
    assert ok.is_valid(), ok.errors
    ok.save()
    policy.refresh_from_db()
    assert policy.handlers == [inside.id]

    outside = MonitorPolicySerializer(policy, data={"handlers": [outsider.id]}, partial=True)
    disabled_ser = MonitorPolicySerializer(policy, data={"handlers": [disabled.id]}, partial=True)
    missing = MonitorPolicySerializer(policy, data={"handlers": [999999]}, partial=True)
    org_change = MonitorPolicySerializer(policy, data={"organizations": [2]}, partial=True)

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
    assert policy.organizations == [1]


def test_alert_list_exposes_handlers_and_display(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
    )
    policy = _policy()
    MonitorAlert.objects.create(
        policy_id=policy.id,
        organizations=[1],
        monitor_instance_id="h1",
        status="new",
        handlers=[user.id],
        content="memory high",
    )
    api_client.cookies["current_team"] = "1"

    alert = MonitorAlert.objects.get(monitor_instance_id="h1")
    resp = api_client.get(
        f"{BASE}/api/monitor_alert/",
        {"status_in": "new", "page": 1, "page_size": 20},
    )
    detail = api_client.get(f"{BASE}/api/monitor_alert/{alert.id}/")

    assert resp.status_code == 200
    result = resp.json()["data"]["results"][0]
    assert result["handlers"] == [user.id]
    assert result["handlers_display"] == ["处理人甲(handler1)"]
    assert detail.status_code == 200
    assert detail.json()["data"]["handlers_display"] == ["处理人甲(handler1)"]


def test_my_alert_filters_handlers_not_operator(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    other = _org_user()
    policy = _policy()
    mine = _new_alert(policy, handlers=[actor.id], monitor_instance_id="mine")
    operator_only = _new_alert(
        policy,
        handlers=[],
        operator="testuser",
        monitor_instance_id="operator-only",
    )
    others = _new_alert(policy, handlers=[other.id], monitor_instance_id="other")
    _new_alert(
        policy,
        handlers=[actor.id],
        organizations=[99],
        monitor_instance_id="hidden",
    )
    api_client.cookies["current_team"] = "1"

    listed = api_client.get(
        f"{BASE}/api/monitor_alert/",
        {"status_in": "new", "page": 1, "page_size": 20},
    )
    mine_listed = api_client.get(
        f"{BASE}/api/monitor_alert/",
        {"status_in": "new", "page": 1, "page_size": 20, "my_alert": "1"},
    )

    listed_ids = {item["id"] for item in listed.json()["data"]["results"]}
    mine_ids = {item["id"] for item in mine_listed.json()["data"]["results"]}
    assert listed.status_code == 200
    assert mine_listed.status_code == 200
    assert listed_ids == {mine.id, operator_only.id, others.id}
    assert mine_ids == {mine.id}


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


def _new_alert(policy, **kwargs):
    kwargs.setdefault("organizations", [1])
    kwargs.setdefault("handlers", [])
    return MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id=kwargs.pop("monitor_instance_id", "h1"),
        status=kwargs.pop("status", "new"),
        **kwargs,
    )


def test_claim_empty_active_alert_then_second_claim_conflicts(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    policy = _policy()
    alert = _new_alert(policy)
    api_client.cookies["current_team"] = "1"

    first = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")
    second = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")

    assert first.status_code == 200
    assert first.json()["data"]["handlers"] == [actor.id]
    assert first.json()["data"]["handlers_display"] == ["测试用户(testuser)"]
    alert.refresh_from_db()
    assert alert.handlers == [actor.id]
    assert alert.operator in (None, "")
    assert second.status_code == 409
    events = api_client.get(f"{BASE}/api/monitor_event/query/{alert.id}/")
    claimed = [item for item in events.json()["data"]["results"] if item["action"] == MonitorEvent.Action.CLAIMED]
    assert len(claimed) == 1
    assert actor.username in claimed[0]["content"]
    assert alert.status == "new"


def test_assign_org_user_succeeds_and_rejects_outsiders(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    notify = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier.notify_assigned")
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    disabled = _org_user(username="disabled1", disabled=True)
    policy = _policy(notice=True)
    alert = _new_alert(policy)
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        ok = api_client.post(
            f"{BASE}/api/monitor_alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )
    alert.refresh_from_db()
    assert ok.status_code == 200
    assert alert.handlers == [inside.id]
    notify.assert_called_once()
    events = api_client.get(f"{BASE}/api/monitor_event/query/{alert.id}/")
    assigned = [item for item in events.json()["data"]["results"] if item["action"] == MonitorEvent.Action.ASSIGNED]
    assert len(assigned) == 1
    assert inside.username in assigned[0]["content"]

    taken = api_client.post(
        f"{BASE}/api/monitor_alert/{alert.id}/assign/",
        {"handlers": [inside.id]},
        format="json",
    )
    assert taken.status_code == 409

    empty = _new_alert(policy, monitor_instance_id="h2")
    outside = api_client.post(
        f"{BASE}/api/monitor_alert/{empty.id}/assign/",
        {"handlers": [outsider.id]},
        format="json",
    )
    disabled_resp = api_client.post(
        f"{BASE}/api/monitor_alert/{empty.id}/assign/",
        {"handlers": [disabled.id]},
        format="json",
    )
    empty.refresh_from_db()
    assert outside.status_code == 400
    assert disabled_resp.status_code == 400
    missing = api_client.post(
        f"{BASE}/api/monitor_alert/{empty.id}/assign/",
        {"handlers": [999999]},
        format="json",
    )
    empty.refresh_from_db()
    assert missing.status_code == 400
    assert empty.handlers == []


def test_handlers_present_blocks_claim_assign_but_close_still_works(api_client, grant_all, mocker):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    mocker.patch("apps.monitor.views.monitor_alert.AlertLifecycleNotifier")
    owner = _org_user()
    policy = _policy()
    alert = _new_alert(policy, handlers=[owner.id])
    api_client.cookies["current_team"] = "1"

    claimed = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")
    assigned = api_client.post(
        f"{BASE}/api/monitor_alert/{alert.id}/assign/",
        {"handlers": [owner.id]},
        format="json",
    )
    closed = api_client.patch(
        f"{BASE}/api/monitor_alert/{alert.id}/",
        {"status": "closed"},
        format="json",
    )

    alert.refresh_from_db()
    assert claimed.status_code == 409
    assert assigned.status_code == 409
    assert closed.status_code == 200
    assert alert.status == "closed"
    assert alert.handlers == [owner.id]
    assert MonitorEvent.objects.filter(alert_id=alert.id, action=MonitorEvent.Action.CLAIMED).count() == 0
    assert MonitorEvent.objects.filter(alert_id=alert.id, action=MonitorEvent.Action.ASSIGNED).count() == 0
    assert MonitorEvent.objects.filter(alert_id=alert.id, action=MonitorEvent.Action.CLOSED).count() == 1


def test_inactive_alert_cannot_claim_or_assign(api_client, grant_all):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    owner = _org_user()
    policy = _policy()
    recovered = _new_alert(policy, status="recovered", monitor_instance_id="r1")
    closed = _new_alert(policy, status="closed", monitor_instance_id="c1")
    api_client.cookies["current_team"] = "1"

    for alert in (recovered, closed):
        claim = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")
        assign = api_client.post(
            f"{BASE}/api/monitor_alert/{alert.id}/assign/",
            {"handlers": [owner.id]},
            format="json",
        )
        alert.refresh_from_db()
        assert claim.status_code == 409
        assert assign.status_code == 409
        assert alert.handlers == []
        assert MonitorEvent.objects.filter(alert_id=alert.id).count() == 0


def test_deleted_policy_allows_claim_and_skips_assign_notify(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    notify = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier.notify_assigned")
    assignee = _org_user()
    policy = _policy(notice=True)
    claim_alert = _new_alert(policy, monitor_instance_id="claim-orphan")
    assign_alert = _new_alert(policy, monitor_instance_id="assign-orphan")
    policy.delete()
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        claimed = api_client.post(f"{BASE}/api/monitor_alert/{claim_alert.id}/claim/")
        assigned = api_client.post(
            f"{BASE}/api/monitor_alert/{assign_alert.id}/assign/",
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
    notify = mocker.patch("apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier.notify_assigned")
    policy = _policy(notice=True)
    alert = _new_alert(policy)
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")

    assert resp.status_code == 200
    notify.assert_not_called()


def test_claim_requires_operate_permission(api_client, grant_all, mocker):
    from apps.core.utils.web_utils import WebUtils

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    _actor_user()
    policy = _policy()
    alert = _new_alert(policy)
    mocker.patch(
        "apps.monitor.views.monitor_alert.MonitorAlertViewSet._authorize_alert_operate",
        return_value=WebUtils.response_403("没有操作该告警的权限"),
    )
    api_client.cookies["current_team"] = "1"

    resp = api_client.post(f"{BASE}/api/monitor_alert/{alert.id}/claim/")

    assert resp.status_code == 403
    alert.refresh_from_db()
    assert alert.handlers == []


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
        config={"method_name": "receive_alert_events"},
        description="",
        team=[1],
    )


def test_assign_sends_notice_to_handlers_not_notice_users(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _person_channel()
    send = mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(
        notice=True,
        notice_type_ids=[channel.id],
        notice_users=["policy-notice-user"],
    )
    alert = _new_alert(policy, notice_type_ids=[channel.id], notice_users=["alert-notice-user"])
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"{BASE}/api/monitor_alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    alert.refresh_from_db()
    assert resp.status_code == 200
    send.assert_called_once()
    channel_id, title, _content, receivers = send.call_args.args
    assert channel_id == channel.id
    assert "分派" in title
    assert receivers == [str(inside.id)]
    assert "policy-notice-user" not in receivers
    assert "alert-notice-user" not in receivers
    assert any(entry.get("action") == "assigned" for entry in (alert.notice_logs or []))


def test_assign_notice_skips_alert_center_and_nats(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    email = _person_channel()
    nats = _alert_center_channel()
    send = mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(notice=True, notice_type_ids=[email.id, nats.id])
    alert = _new_alert(policy, notice_type_ids=[email.id, nats.id])
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"{BASE}/api/monitor_alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert resp.status_code == 200
    assert send.call_count == 1
    assert send.call_args.args[0] == email.id
    assert send.call_args.args[3] == [str(inside.id)]


def test_assign_notice_off_does_not_send(
    api_client, grant_all, mocker, django_capture_on_commit_callbacks
):
    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    send = mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.SystemMgmtUtils.send_msg_with_channel",
        return_value={"result": True},
    )
    inside = _org_user()
    policy = _policy(notice=False, notice_type_ids=[_person_channel().id])
    alert = _new_alert(policy)
    api_client.cookies["current_team"] = "1"

    with django_capture_on_commit_callbacks(execute=True):
        resp = api_client.post(
            f"{BASE}/api/monitor_alert/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert resp.status_code == 200
    send.assert_not_called()


def test_claim_logs_lifecycle_template_without_handler_payload(grant_all, caplog):
    from apps.monitor.services.alert_handlers import claim_alert as claim_alert_service

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    policy = _policy()
    alert = _new_alert(policy)
    caplog.set_level(logging.INFO, logger="monitor")

    claimed = claim_alert_service(alert, actor=actor)

    records = [record for record in caplog.records if record.msg == "event=alert_claimed alert_id=%s"]
    assert claimed.handlers == [actor.id]
    assert len(records) == 1
    assert records[0].args == (alert.pk,)
    rendered = records[0].getMessage()
    assert str(alert.pk) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered


def test_assign_logs_lifecycle_template_without_handler_payload(grant_all, caplog):
    from apps.monitor.services.alert_handlers import assign_alert as assign_alert_service

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    actor = _actor_user()
    inside = _org_user()
    policy = _policy()
    alert = _new_alert(policy)
    caplog.set_level(logging.INFO, logger="monitor")

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
    from apps.monitor.services.alert_lifecycle_notify import AlertLifecycleNotifier

    Group.objects.get_or_create(id=1, defaults={"name": "Default Team", "parent_id": 0})
    channel = _person_channel()
    mocker.patch(
        "apps.monitor.services.alert_lifecycle_notify.AlertLifecycleNotifier._send_normal_notice",
        side_effect=RuntimeError("smtp-password=secret"),
    )
    inside = _org_user()
    policy = _policy(notice=True, notice_type_ids=[channel.id])
    alert = _new_alert(policy, notice_type_ids=[channel.id], handlers=[inside.id])
    caplog.set_level(logging.ERROR, logger="monitor")

    AlertLifecycleNotifier(policy).notify_assigned([alert])

    records = [
        record
        for record in caplog.records
        if record.msg == "event=assign_notify_failed action=assigned channel_id=%s failed_stage=send error_type=%s"
    ]
    assert len(records) == 1
    assert records[0].args == (channel.id, "RuntimeError")
    assert records[0].exc_info is None
    rendered = records[0].getMessage()
    assert "smtp-password=secret" not in rendered
    assert "password" not in rendered.lower()
