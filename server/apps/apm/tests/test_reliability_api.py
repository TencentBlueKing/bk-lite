from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from apps.apm.adapters import InMemoryNotificationDispatcher
from apps.apm.models import ApmAlertOutbox, ApmPolicy, ApmService, ApmServiceOrganization
from apps.apm.services import DjangoApmPolicyService
from apps.apm.services.contracts import NotificationChannel, NotificationRecipient, ServiceRed, SloEvaluation

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


def test_slo_policy_event_delivery_and_recipient_http_path(apm_api_client, mocker):
    service = _service(10)
    now = timezone.now()
    mocker.patch(
        "apps.apm.views.control_plane.DjangoApmReliabilityService.evaluate",
        return_value=SloEvaluation(
            current_rate=99.95,
            budget_remaining=50,
            data_state="available",
            started_at=now - timedelta(days=30),
            ended_at=now,
        ),
    )
    directory = mocker.patch("apps.apm.views.control_plane.ApmPolicyViewSet.notification_directory")
    directory.list_available.return_value = [
        NotificationChannel(
            id=23,
            name="邮件",
            channel_type="email",
            description="值班邮件",
            delivery_mode="message",
            recipient_mode="system_user",
            availability="available",
        )
    ]
    recipients = mocker.patch("apps.apm.views.control_plane.ApmNotificationRecipientViewSet.directory")
    recipients.search_recipients.return_value = [NotificationRecipient(id=42, username="alice", display_name="Alice On-call")]

    slo = apm_api_client.post(
        "/api/v1/apm/slos/",
        {
            "name": "结算可用性",
            "service_id": str(service.id),
            "environment": "production",
            "endpoint": "",
            "sli_type": "availability",
            "objective": "99.900",
            "evaluation_window": "rolling30d",
            "is_enabled": True,
        },
        format="json",
    )
    policy = apm_api_client.post(
        "/api/v1/apm/policies/",
        {
            "name": "生产错误率",
            "service_id": str(service.id),
            "environment": "production",
            "metric_type": "error_rate",
            "metric_window": 2,
            "thresholds": [{"severity": "error", "comparator": "gt", "value": "0.050000"}],
            "trigger_after": 1,
            "recover_after": 2,
            "notification_targets": [{"channel_id": 23, "recipients": ["42"]}],
            "is_enabled": True,
        },
        format="json",
    )
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    evaluator = DjangoApmPolicyService(
        SimpleNamespace(service_red=lambda query: ServiceRed(20, 0.10, 100, 150)),
        InMemoryNotificationDispatcher(),
    )
    evaluator.evaluate(policy.data["id"], evaluated_at=evaluated_at)
    evaluator.retry_pending_events()

    events = apm_api_client.get(
        "/api/v1/apm/events/",
        {
            "action": "triggered",
            "started_at": evaluated_at - timedelta(minutes=1),
            "ended_at": evaluated_at + timedelta(minutes=1),
        },
    )
    deliveries = apm_api_client.get(
        "/api/v1/apm/notification-deliveries/",
        {"event_id": events.data[0]["event_id"], "status": "delivered"},
    )
    recipient_options = apm_api_client.get("/api/v1/apm/notification-recipients/", {"search": "ali", "limit": 20})
    listed_slos = apm_api_client.get("/api/v1/apm/slos/")

    assert slo.status_code == 201
    assert policy.status_code == 201
    assert events.status_code == 200
    assert len(events.data) == 1
    assert events.data[0]["policy_id"] == policy.data["id"]
    assert events.data[0]["service"] == "checkout"
    assert events.data[0]["action"] == "triggered"
    assert events.data[0]["notification_deliveries"][0]["channel_name"] == "邮件"
    assert deliveries.status_code == 200
    assert len(deliveries.data) == 1
    assert deliveries.data[0]["event_id"] == events.data[0]["event_id"]
    assert deliveries.data[0]["status"] == "delivered"
    assert ApmAlertOutbox.objects.filter(event__event_id=events.data[0]["event_id"]).count() == 1
    assert recipient_options.status_code == 200
    assert recipient_options.data == [{"id": 42, "username": "alice", "display_name": "Alice On-call"}]
    assert listed_slos.data[0]["id"] == slo.data["id"]
    assert listed_slos.data[0]["current_rate"] == 99.95
    assert ApmPolicy.objects.filter(id=policy.data["id"]).exists()


def test_notification_recipients_http_reports_directory_outage(apm_api_client, mocker):
    directory = mocker.patch("apps.apm.views.control_plane.ApmNotificationRecipientViewSet.directory")
    directory.search_recipients.side_effect = RuntimeError("system management unavailable")

    response = apm_api_client.get("/api/v1/apm/notification-recipients/")

    assert response.status_code == 503
    assert response.data["code"] == "notification_recipients_unavailable"


def test_events_and_deliveries_are_hidden_outside_current_organization(apm_api_client):
    hidden = _service(20, "billing")
    policy = ApmPolicy.objects.create(
        name="隐藏错误率",
        service=hidden,
        environment="production",
        metric_type="error_rate",
        thresholds=[{"severity": "error", "comparator": "gt", "value": "0.050000"}],
        trigger_after=1,
        recover_after=1,
    )
    evaluated_at = timezone.now().replace(second=0, microsecond=0)
    DjangoApmPolicyService(
        SimpleNamespace(service_red=lambda query: ServiceRed(20, 0.10, 100, 150)),
        InMemoryNotificationDispatcher(),
    ).evaluate(policy.id, evaluated_at=evaluated_at)

    events = apm_api_client.get("/api/v1/apm/events/")
    deliveries = apm_api_client.get("/api/v1/apm/notification-deliveries/")

    assert events.status_code == 200
    assert events.data == []
    assert deliveries.status_code == 200
    assert deliveries.data == []
