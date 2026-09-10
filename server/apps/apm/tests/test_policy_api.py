from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import (
    ApmAlert,
    ApmAlertOutbox,
    ApmNotificationDeliveryRetry,
    ApmPolicy,
    ApmPolicyNotificationTarget,
    ApmService,
    ApmServiceOrganization,
)
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import NotificationChannel, NotificationRecipient, ServiceRed
from apps.apm.tests.helpers import bind_policy_organizations

pytestmark = pytest.mark.django_db


def _service(organization=10, name="checkout"):
    now = timezone.now()
    service = ApmService.objects.create(
        namespace="shop",
        normalized_namespace="shop",
        name=name,
        normalized_name=name,
        first_seen_at=now,
        last_seen_at=now,
    )
    ApmServiceOrganization.objects.create(service=service, organization=organization)
    return service


def _payload(service, organizations=(10,)):
    payload = {
        "name": "生产错误率",
        "service_id": str(service.id),
        "environment": "production",
        "metric_type": "error_rate",
        "metric_window": 2,
        "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.050000"}],
        "trigger_after": 2,
        "recover_after": 2,
        "notification_targets": [],
        "is_enabled": True,
    }
    if organizations is not None:
        payload["organizations"] = list(organizations)
    return payload


def test_policy_create_requires_assignable_organizations(apm_api_client):
    service = _service(10)
    missing = apm_api_client.post("/api/v1/apm/policies/", _payload(service, organizations=None), format="json")
    empty = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "organizations": []},
        format="json",
    )
    forbidden = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "organizations": [99]},
        format="json",
    )
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "organizations": [10, 30]},
        format="json",
    )

    assert missing.status_code == 400
    assert "organizations" in missing.data
    assert empty.status_code == 400
    assert "organizations" in empty.data
    assert forbidden.status_code == 403
    assert created.status_code == 201
    assert created.data["organizations"] == [10, 30]
    assert created.data["handlers"] == []
    assert ApmPolicy.objects.count() == 1


def test_policy_create_persists_handlers(apm_api_client):
    from apps.system_mgmt.models import User

    user = User.objects.create(
        username="handler1",
        display_name="处理人甲",
        email="handler1@example.com",
        password="x",
        group_list=[10],
    )
    service = _service(10)
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "handlers": [user.id]},
        format="json",
    )
    listed = apm_api_client.get("/api/v1/apm/policies/")
    detail = apm_api_client.get(f"/api/v1/apm/policies/{created.data['id']}/")

    assert created.status_code == 201
    assert created.data["handlers"] == [user.id]
    assert listed.data[0]["handlers"] == [user.id]
    assert detail.data["handlers"] == [user.id]
    assert ApmPolicy.objects.get().handlers == [user.id]


def test_policy_save_rejects_handlers_outside_policy_organizations(apm_api_client):
    from apps.system_mgmt.models import User

    inside = User.objects.create(
        username="assignee1",
        display_name="assignee1",
        email="assignee1@example.com",
        password="x",
        group_list=[10],
    )
    outsider = User.objects.create(
        username="outsider",
        display_name="outsider",
        email="outsider@example.com",
        password="x",
        group_list=[99],
    )
    disabled = User.objects.create(
        username="disabled1",
        display_name="disabled1",
        email="disabled1@example.com",
        password="x",
        disabled=True,
        group_list=[10],
    )
    service = _service(10)
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "handlers": [inside.id]},
        format="json",
    )
    assert created.status_code == 201
    assert created.data["handlers"] == [inside.id]
    policy_id = created.data["id"]

    outside = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy_id}/",
        {"handlers": [outsider.id]},
        format="json",
    )
    disabled_resp = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy_id}/",
        {"handlers": [disabled.id]},
        format="json",
    )
    missing = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy_id}/",
        {"handlers": [999999]},
        format="json",
    )
    org_change = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy_id}/",
        {"organizations": [30]},
        format="json",
    )

    assert outside.status_code == 400
    assert "handlers" in outside.data
    assert disabled_resp.status_code == 400
    assert "handlers" in disabled_resp.data
    assert missing.status_code == 400
    assert "handlers" in missing.data
    assert org_change.status_code == 400
    assert "handlers" in org_change.data
    assert ApmPolicy.objects.get().handlers == [inside.id]
    assert list(
        ApmPolicy.objects.get().organization_links.values_list("organization", flat=True)
    ) == [10]


def test_policy_list_and_detail_are_scoped_by_policy_organizations(apm_api_client):
    service = _service(10)
    visible = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "name": "当前组织策略", "organizations": [10]},
        format="json",
    )
    hidden = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "name": "其他组织策略", "organizations": [20]},
        format="json",
    )

    listed = apm_api_client.get("/api/v1/apm/policies/")
    visible_detail = apm_api_client.get(f"/api/v1/apm/policies/{visible.data['id']}/")
    hidden_detail = apm_api_client.get(f"/api/v1/apm/policies/{hidden.data['id']}/")
    apm_api_client.cookies["current_team"] = "20"
    other_team = apm_api_client.get("/api/v1/apm/policies/")

    assert visible.status_code == 201
    assert hidden.status_code == 201
    assert [item["id"] for item in listed.data] == [visible.data["id"]]
    assert visible_detail.status_code == 200
    assert visible_detail.data["organizations"] == [10]
    assert hidden_detail.status_code == 404
    assert [item["id"] for item in other_team.data] == [hidden.data["id"]]
    assert other_team.data[0]["organizations"] == [20]


def test_policy_update_keeps_organizations_unless_explicitly_sent(apm_api_client):
    service = _service(10)
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "organizations": [10]},
        format="json",
    )
    preserved = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"name": "只改名称"},
        format="json",
    )
    replaced = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"organizations": [10, 20]},
        format="json",
    )

    assert created.status_code == 201
    assert preserved.status_code == 200
    assert preserved.data["organizations"] == [10]
    assert replaced.status_code == 200
    assert replaced.data["organizations"] == [10, 20]


def test_new_alert_snapshots_policy_organizations_not_service(apm_api_client):
    service = _service(10)
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "organizations": [30], "trigger_after": 1},
        format="json",
    )
    apm_api_client.cookies["current_team"] = "30"
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    evaluator = DjangoApmPolicyService(
        SimpleNamespace(service_red=lambda query: ServiceRed(20, 0.10, 100, 150)),
        InMemoryNotificationDispatcher(),
    )

    evaluator.evaluate(created.data["id"], evaluated_at=evaluated_at)
    first_alert = ApmAlert.objects.get()
    ApmServiceOrganization.objects.filter(service=service).delete()
    ApmServiceOrganization.objects.create(service=service, organization=20)
    evaluator.evaluate(created.data["id"], evaluated_at=evaluated_at + timedelta(minutes=1))
    first_alert.refresh_from_db()
    policy_after_service_change = apm_api_client.get(f"/api/v1/apm/policies/{created.data['id']}/")
    apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"organizations": [10]},
        format="json",
    )
    evaluator.evaluate(created.data["id"], evaluated_at=evaluated_at + timedelta(minutes=2))
    apm_api_client.cookies["current_team"] = "10"
    first_alert.refresh_from_db()
    later_alert = ApmAlert.objects.exclude(id=first_alert.id).get()
    policy_after_update = apm_api_client.get(f"/api/v1/apm/policies/{created.data['id']}/")

    assert created.status_code == 201
    assert first_alert.organizations == [30]
    assert first_alert.events.filter(action="triggered").get().organizations == [30]
    assert policy_after_service_change.status_code == 200
    assert policy_after_service_change.data["organizations"] == [30]
    assert policy_after_update.status_code == 200
    assert policy_after_update.data["organizations"] == [10]
    assert later_alert.organizations == [10]


def test_new_alert_snapshots_policy_handlers(apm_api_client):
    from apps.system_mgmt.models import User

    first = User.objects.create(
        username="snap-handler-1",
        display_name="snap-1",
        email="snap1@example.com",
        password="x",
        group_list=[10],
    )
    second = User.objects.create(
        username="snap-handler-2",
        display_name="snap-2",
        email="snap2@example.com",
        password="x",
        group_list=[10],
    )
    service = _service(10)
    created = apm_api_client.post(
        "/api/v1/apm/policies/",
        {**_payload(service), "handlers": [first.id, second.id], "trigger_after": 1},
        format="json",
    )
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    evaluator = DjangoApmPolicyService(
        SimpleNamespace(service_red=lambda query: ServiceRed(20, 0.10, 100, 150)),
        InMemoryNotificationDispatcher(),
    )

    evaluator.evaluate(created.data["id"], evaluated_at=evaluated_at)
    first_alert = ApmAlert.objects.get()
    policy = ApmPolicy.objects.get(id=created.data["id"])
    policy.handlers = [9]
    policy.save(update_fields=("handlers", "updated_at"))
    evaluator.evaluate(created.data["id"], evaluated_at=evaluated_at + timedelta(minutes=1))
    first_alert.refresh_from_db()

    assert created.status_code == 201
    assert first_alert.handlers == [first.id, second.id]
    assert ApmAlert.objects.count() == 1


def test_policy_crud_is_scoped_by_service_organization(apm_api_client):
    visible_service = _service(10)
    hidden_service = _service(20, "billing")

    created = apm_api_client.post("/api/v1/apm/policies/", _payload(visible_service), format="json")
    hidden = apm_api_client.post("/api/v1/apm/policies/", _payload(hidden_service), format="json")
    listed = apm_api_client.get("/api/v1/apm/policies/")

    assert created.status_code == 201
    assert created.data["service_name"] == "checkout"
    assert created.data["state"]["status"] == "normal"
    assert hidden.status_code == 404
    assert [item["id"] for item in listed.data] == [created.data["id"]]

    disabled = apm_api_client.post(f"/api/v1/apm/policies/{created.data['id']}/disable/")
    assert disabled.status_code == 200
    assert disabled.data["is_enabled"] is False

    updated = apm_api_client.patch(
        f"/api/v1/apm/policies/{created.data['id']}/",
        {"thresholds": [{"severity": "error", "comparator": "gt", "value": "0.100000"}]},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["thresholds"][0]["value"] == "0.100000"

    deleted = apm_api_client.delete(f"/api/v1/apm/policies/{created.data['id']}/")
    # 全局 API envelope 将空响应规范化为 200。
    assert deleted.status_code == 200
    assert ApmPolicy.objects.count() == 0


def test_policy_mutation_requires_operate_permission(apm_user):
    apm_user.permission["apm"] = {"policies-View"}
    client = APIClient()
    client.force_authenticate(user=apm_user)
    client.cookies["current_team"] = "10"

    response = client.post("/api/v1/apm/policies/", _payload(_service(10)), format="json")

    assert response.status_code == 403
    assert ApmPolicy.objects.count() == 0


def test_error_rate_threshold_is_bounded(apm_api_client):
    payload = _payload(_service(10))
    payload["thresholds"][0]["value"] = "1.100000"

    response = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert response.status_code == 400
    assert "thresholds" in response.data


def test_policy_persists_no_data_alert_name(apm_api_client):
    payload = _payload(_service(10))
    payload.update(
        {
            "no_data_after": 5,
            "no_data_severity": "warning",
            "no_data_alert_name": "${service} ${metric} 无数据告警",
        }
    )

    response = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert response.status_code == 201
    assert response.data["no_data_alert_name"] == "${service} ${metric} 无数据告警"
    assert ApmPolicy.objects.get(id=response.data["id"]).no_data_alert_name == "${service} ${metric} 无数据告警"


def test_policy_rejects_removed_legacy_notification_fields(apm_api_client):
    payload = _payload(_service(10))
    payload["notice"] = True

    response = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert response.status_code == 400
    assert response.data["notice"] == "APM 策略不支持该字段。"


def test_policy_notification_channel_is_revalidated_in_current_scope(apm_api_client, mocker):
    directory = mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet.notification_directory")
    directory.list_available.return_value = [
        SimpleNamespace(
            id=23,
            name="邮件",
            channel_type="email",
            description="值班邮件",
            delivery_mode="message",
            recipient_mode="system_user",
            availability="available",
        )
    ]
    payload = _payload(_service(10))
    payload.update(
        {
            "notification_targets": [{"channel_id": 99, "recipients": ["42"]}],
        }
    )

    denied = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")
    payload["notification_targets"] = [{"channel_id": 23, "recipients": ["42"]}]
    created = apm_api_client.post("/api/v1/apm/policies/", payload, format="json")

    assert denied.status_code == 400
    assert "notification_targets" in denied.data
    assert created.status_code == 201
    assert created.data["notification_targets"] == [
        {
            "channel_id": 23,
            "channel_name": "邮件",
            "channel_type": "email",
            "delivery_mode": "message",
            "recipient_mode": "system_user",
            "recipients": ["42"],
        }
    ]
    assert ApmPolicyNotificationTarget.objects.filter(policy_id=created.data["id"]).count() == 1


def test_notification_directory_outage_only_blocks_notification_configuration(apm_api_client, mocker):
    service = _service(10)
    policy = ApmPolicy.objects.create(
        name="生产错误率",
        service=service,
        environment="production",
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.050000"}],
        trigger_after=2,
        recover_after=2,
    )
    bind_policy_organizations(policy)
    directory = mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet.notification_directory")
    directory.list_available.side_effect = RuntimeError("system management unavailable")

    ordinary_update = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy.id}/",
        {"name": "更新后的策略"},
        format="json",
    )
    notification_update = apm_api_client.patch(
        f"/api/v1/apm/policies/{policy.id}/",
        {"notification_targets": [{"channel_id": 24, "recipients": []}]},
        format="json",
    )

    assert ordinary_update.status_code == 200
    assert notification_update.status_code == 503
    assert notification_update.data["code"] == "notification_channels_unavailable"


def test_policy_test_query_uses_controlled_metric_service(apm_api_client, mocker):
    created = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(10)), format="json")
    query_result = SimpleNamespace(
        value=Decimal("0.125"),
        breached=True,
        evaluated_at=timezone.now(),
        data_state="available",
    )
    service = mocker.Mock()
    service.test_query.return_value = query_result
    mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet._service", return_value=service)

    response = apm_api_client.post(f"/api/v1/apm/policies/{created.data['id']}/test-query/")

    assert response.status_code == 200
    assert response.data["value"] == "0.125"
    assert response.data["breached"] is True
    assert response.data["data_state"] == "available"


def test_policy_test_query_exposes_no_data_without_fabricating_a_zero(apm_api_client, mocker):
    created = apm_api_client.post("/api/v1/apm/policies/", _payload(_service(10)), format="json")
    service = mocker.Mock()
    service.test_query.return_value = SimpleNamespace(
        value=None,
        breached=None,
        evaluated_at=timezone.now(),
        data_state="no_data",
    )
    mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet._service", return_value=service)

    response = apm_api_client.post(f"/api/v1/apm/policies/{created.data['id']}/test-query/")

    assert response.status_code == 200
    assert response.data["data_state"] == "no_data"
    assert response.data["value"] is None
    assert response.data["breached"] is None


def test_event_view_uses_current_organization_and_apm_reader(apm_api_client, mocker):
    event = {
        "id": 1,
        "event_id": "EVENT-1",
        "title": "APM 生产错误率触发",
        "severity": "error",
        "action": "triggered",
    }
    reader = mocker.patch("apps.apm.views.control_plane.ApmEventViewSet.reader")
    reader.list.return_value = [event]

    response = apm_api_client.get("/api/v1/apm/events/?action=triggered&severity=error&limit=20")

    assert response.status_code == 200
    assert response.data == [event]
    call = reader.list.call_args.kwargs
    assert set(call["organization_ids"]) == {10}
    assert "organization_id" not in call
    assert call["action"] == "triggered"
    assert call["severity"] == "error"
    assert call["limit"] == 20


def test_event_view_rejects_unknown_actions(apm_api_client, mocker):
    reader = mocker.patch("apps.apm.views.control_plane.ApmEventViewSet.reader")

    response = apm_api_client.get("/api/v1/apm/events/?action=acknowledged")

    assert response.status_code == 400
    reader.list.assert_not_called()


def test_policy_trigger_is_queryable_from_apm_owned_event_api(apm_api_client):
    service = _service(10)
    policy = ApmPolicy.objects.create(
        **{
            key: value
            for key, value in _payload(service).items()
            if key not in {"service_id", "is_enabled", "notification_targets", "trigger_after", "organizations"}
        },
        service=service,
        trigger_after=1,
    )
    bind_policy_organizations(policy)
    metric_store = SimpleNamespace(
        service_red=lambda query: ServiceRed(
            request_rate=20,
            error_rate=0.10,
            p95_ms=100,
            p99_ms=150,
        )
    )
    evaluator = DjangoApmPolicyService(metric_store, InMemoryNotificationDispatcher())
    evaluated_at = timezone.now().replace(second=0, microsecond=0)

    evaluator.evaluate(policy.id, evaluated_at=evaluated_at)
    response = apm_api_client.get(
        "/api/v1/apm/events/",
        {"started_at": evaluated_at - timedelta(minutes=1), "ended_at": evaluated_at + timedelta(minutes=1)},
    )

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["policy_id"] == str(policy.id)
    assert response.data[0]["service"] == "checkout"
    assert response.data[0]["action"] == "triggered"


def test_notification_channel_view_uses_current_organization_scope(apm_api_client, mocker):
    directory = mocker.patch("apps.apm.views.control_plane.ApmNotificationChannelViewSet.directory")
    directory.list_available.return_value = [
        NotificationChannel(
            id=23,
            name="告警中心",
            channel_type="nats",
            description="事件副本",
            delivery_mode="alert_event_copy",
            recipient_mode="none",
            availability="available",
        )
    ]

    response = apm_api_client.get("/api/v1/apm/notification-channels/")

    assert response.status_code == 200
    assert response.data[0]["id"] == 23
    call = directory.list_available.call_args.kwargs
    assert call["organization_id"] == 10
    assert call["actor_context"]["current_team"] == 10


def test_notification_recipient_view_returns_scoped_stable_user_options(apm_api_client, mocker):
    directory = mocker.patch("apps.apm.views.control_plane.ApmNotificationRecipientViewSet.directory")
    directory.search_recipients.return_value = [NotificationRecipient(id=42, username="alice", display_name="Alice On-call")]

    response = apm_api_client.get("/api/v1/apm/notification-recipients/?search=ali&limit=20")

    assert response.status_code == 200
    assert response.data == [{"id": 42, "username": "alice", "display_name": "Alice On-call"}]
    call = directory.search_recipients.call_args.kwargs
    assert call["organization_id"] == 10
    assert call["search"] == "ali"
    assert call["limit"] == 20


def test_notification_recipients_accept_policy_organization_ids(apm_api_client, mocker):
    directory = mocker.patch("apps.apm.views.control_plane.ApmNotificationRecipientViewSet.directory")
    directory.search_recipients.return_value = [NotificationRecipient(id=7, username="bob", display_name="Bob")]

    ok = apm_api_client.get("/api/v1/apm/notification-recipients/?organization_ids=10,30")
    forbidden = apm_api_client.get("/api/v1/apm/notification-recipients/?organization_ids=99")

    assert ok.status_code == 200
    assert ok.data == [{"id": 7, "username": "bob", "display_name": "Bob"}]
    assert directory.search_recipients.call_args.kwargs["organization_ids"] == [10, 30]
    assert forbidden.status_code == 403


def test_notification_delivery_status_and_manual_retry_are_real_and_scoped(apm_api_client, apm_user):
    service = _service(10)
    policy = ApmPolicy.objects.create(
        **{
            key: value
            for key, value in _payload(service).items()
            if key not in {"service_id", "is_enabled", "notification_targets", "trigger_after", "organizations"}
        },
        service=service,
        trigger_after=1,
    )
    bind_policy_organizations(policy)
    ApmPolicyNotificationTarget.objects.create(
        policy=policy,
        channel_id=31,
        channel_name="Webhook",
        channel_type="custom_webhook",
        delivery_mode="message",
        recipient_mode="free_text",
        recipients=["on-call"],
    )
    evaluator = DjangoApmPolicyService(
        SimpleNamespace(service_red=lambda query: ServiceRed(20, 0.10, 100, 150)),
        InMemoryNotificationDispatcher(),
    )
    evaluator.evaluate(policy.id, evaluated_at=timezone.now().replace(second=0, microsecond=0))
    delivery = ApmAlertOutbox.objects.get()
    delivery.delivery_status = ApmAlertOutbox.DeliveryStatus.FAILED
    delivery.attempts = 8
    delivery.last_error_code = "provider_unavailable"
    delivery.last_error_message = "temporarily down"
    delivery.failed_at = timezone.now()
    delivery.save()

    listed = apm_api_client.get("/api/v1/apm/notification-deliveries/")
    retried = apm_api_client.post(
        f"/api/v1/apm/notification-deliveries/{delivery.id}/retry/",
        {"recipients": ["new-on-call"]},
        format="json",
    )

    assert listed.status_code == 200
    assert listed.data[0]["status"] == "failed"
    assert listed.data[0]["channel_name"] == "Webhook"
    assert listed.data[0]["event_id"] == delivery.event.event_id
    events = apm_api_client.get("/api/v1/apm/events/")
    assert events.status_code == 200
    assert events.data[0]["notification_deliveries"][0]["id"] == delivery.id
    assert retried.status_code == 200
    assert retried.data["status"] == "pending"
    assert retried.data["attempts"] == 0
    delivery.refresh_from_db()
    assert delivery.recipients == ["new-on-call"]
    assert ApmNotificationDeliveryRetry.objects.filter(
        delivery=delivery,
        previous_attempts=8,
        previous_error_code="provider_unavailable",
    ).exists()

    conflict = apm_api_client.post(f"/api/v1/apm/notification-deliveries/{delivery.id}/retry/", {}, format="json")
    assert conflict.status_code == 409
    assert conflict.data["code"] == "state_conflict"

    apm_api_client.cookies["current_team"] = "20"
    assert apm_api_client.get("/api/v1/apm/notification-deliveries/").data == []
    hidden = apm_api_client.post(f"/api/v1/apm/notification-deliveries/{delivery.id}/retry/", {}, format="json")
    assert hidden.status_code == 404

    apm_api_client.cookies["current_team"] = "10"
    apm_user.permission["apm"] = {"events-View", "policies-View"}
    denied = apm_api_client.post(f"/api/v1/apm/notification-deliveries/{delivery.id}/retry/", {}, format="json")
    assert denied.status_code == 403
