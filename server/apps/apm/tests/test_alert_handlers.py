from datetime import timedelta

import logging

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmEvent,
    ApmEventSnapshot,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import ServiceRed, ServiceRedPoint
from apps.apm.tests.helpers import bind_policy_organizations
from apps.system_mgmt.models import User

pytestmark = pytest.mark.django_db


class MetricStore:
    def __init__(self, at):
        self.red = ServiceRed(10, 0.2, 100, 150, (ServiceRedPoint(at, 10, 0.2, 100, 150),))

    def service_red(self, query):
        return self.red


def _trigger(*, organization=10, suffix=""):
    at = timezone.now().replace(second=0, microsecond=0)
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=f"checkout-{organization}{suffix}",
        normalized_name=f"checkout-{organization}{suffix}",
        first_seen_at=at,
        last_seen_at=at,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    policy = ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="production",
        endpoints=["POST /checkout"],
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.1"}],
        trigger_after=1,
        recover_after=1,
    )
    bind_policy_organizations(policy, (organization,))
    DjangoApmPolicyService(MetricStore(at), InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=at)
    return policy, ApmAlert.objects.get(policy=policy), at


def _actor_user():
    return User.objects.create(
        username="apm-user",
        display_name="APM 用户",
        email="apm-user@example.com",
        password="x",
        group_list=[10],
    )


def _org_user(*, username="assignee1", organization=10, disabled=False):
    return User.objects.create(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        password="x",
        disabled=disabled,
        group_list=[organization],
    )


def _person_channel(policy):
    return ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=7,
        channel_name="邮件",
        channel_type="email",
        delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.MESSAGE,
        recipient_mode=ApmPolicyNotificationTarget.RecipientMode.SYSTEM_USER,
        recipients=["1"],
    )


def test_claim_empty_active_alert_then_second_claim_conflicts(apm_api_client):
    actor = _actor_user()
    _, alert, _ = _trigger(suffix="-claim")

    first = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")
    second = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")

    assert first.status_code == 200
    assert first.data["handlers"] == [actor.id]
    alert.refresh_from_db()
    assert alert.handlers == [actor.id]
    assert alert.operator == ""
    assert second.status_code == 409
    claimed_events = [item for item in first.data["events"] if item["action"] == ApmEvent.Action.CLAIMED]
    assert [item["action"] for item in first.data["events"]].count(ApmEvent.Action.TRIGGERED) == 1
    assert len(claimed_events) == 1
    assert actor.username in claimed_events[0]["description"]
    assert alert.status == ApmAlert.Status.ACTIVE
    assert ApmEventSnapshot.objects.filter(alert=alert).count() == 1
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.CLAIMED).count() == 1


def test_assign_org_user_succeeds_and_rejects_outsiders(
    apm_api_client, mocker, django_capture_on_commit_callbacks
):
    notify = mocker.patch("apps.apm.services.alerts.DjangoApmAlertService.notify_assigned")
    inside = _org_user()
    outsider = _org_user(username="outsider", organization=99)
    disabled = _org_user(username="disabled1", disabled=True)
    policy, alert, _ = _trigger(suffix="-assign")
    _person_channel(policy)

    with django_capture_on_commit_callbacks(execute=True):
        ok = apm_api_client.post(
            f"/api/v1/apm/alerts/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )
    alert.refresh_from_db()
    assert ok.status_code == 200
    assert alert.handlers == [inside.id]
    notify.assert_called_once()

    taken = apm_api_client.post(
        f"/api/v1/apm/alerts/{alert.id}/assign/",
        {"handlers": [inside.id]},
        format="json",
    )
    assert taken.status_code == 409

    _, empty, _ = _trigger(suffix="-assign-empty")
    outside = apm_api_client.post(
        f"/api/v1/apm/alerts/{empty.id}/assign/",
        {"handlers": [outsider.id]},
        format="json",
    )
    disabled_resp = apm_api_client.post(
        f"/api/v1/apm/alerts/{empty.id}/assign/",
        {"handlers": [disabled.id]},
        format="json",
    )
    empty.refresh_from_db()
    assert outside.status_code == 400
    assert disabled_resp.status_code == 400
    missing = apm_api_client.post(
        f"/api/v1/apm/alerts/{empty.id}/assign/",
        {"handlers": [999999]},
        format="json",
    )
    empty.refresh_from_db()
    assert missing.status_code == 400
    assert empty.handlers == []


def test_handlers_present_blocks_claim_assign_but_close_still_works(apm_api_client):
    owner = _org_user()
    _, alert, _ = _trigger(suffix="-owned")
    alert.handlers = [owner.id]
    alert.save(update_fields=("handlers", "updated_at"))

    claimed = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")
    assigned = apm_api_client.post(
        f"/api/v1/apm/alerts/{alert.id}/assign/",
        {"handlers": [owner.id]},
        format="json",
    )
    closed = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/close/")

    alert.refresh_from_db()
    assert claimed.status_code == 409
    assert assigned.status_code == 409
    assert closed.status_code == 200
    assert alert.status == ApmAlert.Status.CLOSED
    assert alert.handlers == [owner.id]
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.CLAIMED).count() == 0
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.ASSIGNED).count() == 0
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.CLOSED).count() == 1


def test_inactive_alert_cannot_claim_or_assign(apm_api_client):
    owner = _org_user()
    _, recovered, at = _trigger(suffix="-recovered")
    recovered.status = ApmAlert.Status.RECOVERED
    recovered.ended_at = at + timedelta(minutes=1)
    recovered.save(update_fields=("status", "ended_at", "updated_at"))
    _, closed, _ = _trigger(suffix="-closed")
    closed.status = ApmAlert.Status.CLOSED
    closed.save(update_fields=("status", "updated_at"))

    for alert in (recovered, closed):
        claim = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")
        assign = apm_api_client.post(
            f"/api/v1/apm/alerts/{alert.id}/assign/",
            {"handlers": [owner.id]},
            format="json",
        )
        alert.refresh_from_db()
        assert claim.status_code == 409
        assert assign.status_code == 409
        assert alert.handlers == []


def test_deleted_policy_allows_claim_and_skips_assign_notify(
    apm_api_client, mocker, django_capture_on_commit_callbacks
):
    actor = _actor_user()
    notify = mocker.patch("apps.apm.services.alerts.DjangoApmAlertService.notify_assigned")
    assignee = _org_user()
    claim_policy, claim_alert, _ = _trigger(suffix="-claim-orphan")
    assign_policy, assign_alert, _ = _trigger(suffix="-assign-orphan")
    _person_channel(assign_policy)
    claim_policy.delete()
    assign_policy.delete()

    with django_capture_on_commit_callbacks(execute=True):
        claimed = apm_api_client.post(f"/api/v1/apm/alerts/{claim_alert.id}/claim/")
        assigned = apm_api_client.post(
            f"/api/v1/apm/alerts/{assign_alert.id}/assign/",
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


def test_claim_requires_operate_permission(apm_user):
    _actor_user()
    _, alert, _ = _trigger(suffix="-no-operate")
    apm_user.permission["apm"] = {"events-View"}
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"

    response = client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")

    assert response.status_code == 403
    alert.refresh_from_db()
    assert alert.handlers == []


def _alert_center_channel(policy):
    return ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=8,
        channel_name="告警中心",
        channel_type="nats",
        delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.ALERT_EVENT_COPY,
        recipient_mode=ApmPolicyNotificationTarget.RecipientMode.NONE,
        recipients=[],
    )


def _none_recipient_channel(policy):
    return ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=9,
        channel_name="Webhook",
        channel_type="custom_webhook",
        delivery_mode=ApmPolicyNotificationTarget.DeliveryMode.MESSAGE,
        recipient_mode=ApmPolicyNotificationTarget.RecipientMode.NONE,
        recipients=[],
    )


def test_assign_enqueues_person_channel_outbox_for_handlers(
    apm_api_client, django_capture_on_commit_callbacks
):
    inside = _org_user()
    policy, alert, _ = _trigger(suffix="-assign-notice")
    person = _person_channel(policy)
    _alert_center_channel(policy)
    _none_recipient_channel(policy)
    before = set(ApmAlertOutbox.objects.values_list("event_key", flat=True))

    with django_capture_on_commit_callbacks(execute=True):
        response = apm_api_client.post(
            f"/api/v1/apm/alerts/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    created = ApmAlertOutbox.objects.exclude(event_key__in=before)
    assert response.status_code == 200
    assert created.count() == 1
    outbox = created.get()
    assert outbox.channel_id == person.channel_id
    assert outbox.delivery_mode == ApmPolicyNotificationTarget.DeliveryMode.MESSAGE
    assert outbox.recipients == [str(inside.id)]
    assert outbox.payload.get("action") == "assigned"
    assert outbox.event_id is None
    assigned_events = [item for item in response.data["events"] if item["action"] == ApmEvent.Action.ASSIGNED]
    assert len(assigned_events) == 1
    assert inside.username in assigned_events[0]["description"]
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.ASSIGNED).count() == 1
    assert ApmEventSnapshot.objects.filter(alert=alert, action=ApmEvent.Action.ASSIGNED).count() == 0
    assert alert.status == ApmAlert.Status.ACTIVE


def test_assign_skips_outbox_without_person_channel(
    apm_api_client, django_capture_on_commit_callbacks
):
    inside = _org_user()
    policy, alert, _ = _trigger(suffix="-assign-no-person")
    _alert_center_channel(policy)
    _none_recipient_channel(policy)
    before = ApmAlertOutbox.objects.count()

    with django_capture_on_commit_callbacks(execute=True):
        response = apm_api_client.post(
            f"/api/v1/apm/alerts/{alert.id}/assign/",
            {"handlers": [inside.id]},
            format="json",
        )

    assert response.status_code == 200
    assert ApmAlertOutbox.objects.count() == before
    assert not ApmAlertOutbox.objects.filter(event_key__startswith="assign:").exists()


def test_create_alert_does_not_enqueue_assign_outbox():
    at = timezone.now().replace(second=0, microsecond=0)
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name="checkout-create-no-assign",
        normalized_name="checkout-create-no-assign",
        first_seen_at=at,
        last_seen_at=at,
    )
    ApmServiceOrganization.objects.create(service=service, organization=10)
    policy = ApmPolicy.objects.create(
        name="错误率",
        service=service,
        environment="production",
        endpoints=["POST /checkout"],
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.1"}],
        trigger_after=1,
        recover_after=1,
        handlers=[99],
    )
    bind_policy_organizations(policy, (10,))
    _person_channel(policy)
    DjangoApmPolicyService(MetricStore(at), InMemoryNotificationDispatcher()).evaluate(policy.id, evaluated_at=at)

    alert = ApmAlert.objects.get(policy=policy)
    outbox = ApmAlertOutbox.objects.get()
    assert alert.handlers == [99]
    assert outbox.payload["action"] == "triggered"
    assert outbox.recipients == ["1"]
    assert not str(outbox.event_key).startswith("assign:")
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.ASSIGNED).count() == 0
    assert ApmEvent.objects.filter(alert=alert, action=ApmEvent.Action.CLAIMED).count() == 0


def test_claim_does_not_send_assign_notify(apm_api_client, mocker, django_capture_on_commit_callbacks):
    _actor_user()
    notify = mocker.patch("apps.apm.services.alerts.DjangoApmAlertService.notify_assigned")
    policy, alert, _ = _trigger(suffix="-claim-silent")
    _person_channel(policy)

    with django_capture_on_commit_callbacks(execute=True):
        response = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")

    assert response.status_code == 200
    notify.assert_not_called()


def test_claim_logs_lifecycle_template_without_handler_payload(apm_api_client, caplog):
    from apps.apm.services.alerts import DjangoApmAlertService

    actor = _actor_user()
    _, alert, _ = _trigger(suffix="-claim-log")
    caplog.set_level(logging.INFO, logger="apm")

    claimed = DjangoApmAlertService.claim(alert, actor=actor)

    records = [record for record in caplog.records if record.msg == "event=alert_claimed alert_id=%s"]
    assert claimed.handlers == [actor.id]
    assert len(records) == 1
    assert records[0].args == (alert.id,)
    rendered = records[0].getMessage()
    assert str(alert.id) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered


def test_my_alert_filters_handlers_not_operator(apm_api_client):
    actor = _actor_user()
    other = _org_user()
    _, mine, _ = _trigger(suffix="-mine")
    mine.handlers = [actor.id]
    mine.save(update_fields=("handlers", "updated_at"))
    _, operator_only, _ = _trigger(suffix="-operator")
    operator_only.operator = "apm-user"
    operator_only.save(update_fields=("operator", "updated_at"))
    _, others, _ = _trigger(suffix="-other")
    others.handlers = [other.id]
    others.save(update_fields=("handlers", "updated_at"))
    _, hidden, _ = _trigger(organization=20, suffix="-hidden")
    hidden.handlers = [actor.id]
    hidden.save(update_fields=("handlers", "updated_at"))

    listed = apm_api_client.get("/api/v1/apm/alerts/")
    mine_listed = apm_api_client.get("/api/v1/apm/alerts/", {"my_alert": "1"})
    listed_distribution = apm_api_client.get("/api/v1/apm/alerts/distribution/")
    mine_distribution = apm_api_client.get("/api/v1/apm/alerts/distribution/", {"my_alert": "1"})

    listed_ids = {str(item["id"]) for item in listed.data}
    mine_ids = {str(item["id"]) for item in mine_listed.data}
    assert listed.status_code == 200
    assert mine_listed.status_code == 200
    assert listed_distribution.status_code == 200
    assert mine_distribution.status_code == 200
    assert listed_ids == {str(mine.id), str(operator_only.id), str(others.id)}
    assert mine_ids == {str(mine.id)}
    assert str(hidden.id) not in listed_ids
    assert sum(bucket["error"] for bucket in listed_distribution.data) == 3
    assert sum(bucket["error"] for bucket in mine_distribution.data) == 1


def test_claim_does_not_increase_distribution_count(apm_api_client):
    actor = _actor_user()
    _, alert, _ = _trigger(suffix="-claim-dist")

    before = apm_api_client.get("/api/v1/apm/alerts/distribution/", {"status_group": "active"})
    claimed = apm_api_client.post(f"/api/v1/apm/alerts/{alert.id}/claim/")
    after = apm_api_client.get("/api/v1/apm/alerts/distribution/", {"status_group": "active"})

    assert claimed.status_code == 200
    assert claimed.data["handlers"] == [actor.id]
    assert before.status_code == 200
    assert after.status_code == 200
    assert sum(bucket["error"] for bucket in before.data) == 1
    assert sum(bucket["error"] for bucket in after.data) == 1


def test_assign_logs_lifecycle_template_without_handler_payload(apm_api_client, caplog):
    from apps.apm.services.alerts import DjangoApmAlertService

    actor = _actor_user()
    inside = _org_user()
    _, alert, _ = _trigger(suffix="-assign-log")
    caplog.set_level(logging.INFO, logger="apm")

    assigned = DjangoApmAlertService.assign(alert, handlers=[inside.id], actor=actor)

    records = [
        record
        for record in caplog.records
        if record.msg == "event=alert_assigned alert_id=%s handler_count=%s"
    ]
    assert assigned.handlers == [inside.id]
    assert len(records) == 1
    assert records[0].args == (alert.id, 1)
    rendered = records[0].getMessage()
    assert str(alert.id) in rendered
    assert "password" not in rendered.lower()
    assert "handlers" not in rendered
