"""监控策略 / 告警 handlers 序列化。"""

import logging

import pytest

from apps.monitor.models.monitor_object import MonitorObject
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy, PolicyOrganization
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.system_mgmt.models import Group, User

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

    resp = api_client.get(
        f"{BASE}/api/monitor_alert/",
        {"status_in": "new", "page": 1, "page_size": 20},
    )

    assert resp.status_code == 200
    result = resp.json()["data"]["results"][0]
    assert result["handlers"] == [user.id]
    assert result["handlers_display"] == ["处理人甲(handler1)"]


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
    alert.refresh_from_db()
    assert alert.handlers == [actor.id]
    assert alert.operator in (None, "")
    assert second.status_code == 409


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
    assert str(actor.id) not in rendered
