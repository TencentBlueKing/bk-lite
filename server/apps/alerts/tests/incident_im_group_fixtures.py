import uuid

import pytest

from apps.alerts.models import Incident, IncidentIMGroup
from apps.base.models import User as AuthUser
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationUserMapping, IntegrationInstance
from apps.system_mgmt.models import User as IMUser


@pytest.fixture(autouse=True)
def current_team(api_client):
    api_client.cookies["current_team"] = "1"


@pytest.fixture(autouse=True)
def disable_outbox_broker(monkeypatch):
    monkeypatch.setattr("apps.alerts.service.outbox._schedule_delivery", lambda record_id: None)


def group_url(incident):
    return f"/api/v1/alerts/api/incident/{incident.id}/im-group/"


@pytest.fixture
def operator(db):
    user = AuthUser.objects.create_user(username="operator", password="test-pass", domain="domain.com", group_list=[{"id": 1, "name": "Team 1"}],)
    user.permission = {"alarm": {"Incidents-View", "Incidents-Edit"}}
    return user


@pytest.fixture
def collaborator(db):
    user = AuthUser.objects.create_user(username="collaborator", password="test-pass", domain="domain.com", group_list=[{"id": 1, "name": "Team 1"}],)
    user.permission = {"alarm": {"Incidents-View", "Incidents-Edit"}}
    return user


@pytest.fixture
def superuser(db):
    return AuthUser.objects.create_user(username="superuser", password="test-pass", domain="domain.com", is_superuser=True,)


@pytest.fixture
def incident(db):
    return Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}",
        level="warning",
        title="Incident IM API 测试",
        operator=["operator"],
        collaborators=["collaborator"],
        team=[1],
    )


@pytest.fixture
def channel(db):
    instance = IntegrationInstance.objects.create(
        name=f"feishu-{uuid.uuid4().hex}",
        provider_key="feishu",
        enabled=True,
        status="ready",
        capability_status={"im_notification": "ready", "im_group": "ready"},
    )
    return IMNotificationChannel.objects.create(
        name=f"channel-{uuid.uuid4().hex}", integration_instance=instance, enabled=True, status="ready", external_receive_field="open_id", team=[1],
    )


@pytest.fixture
def operator_mapping(channel):
    user = IMUser.objects.create(username="operator", display_name="Operator", email="operator@example.com", password="test-pass",)
    return IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="open_id",
        external_identity_value="operator",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_operator"},
    )


def create_payload(channel, **overrides):
    return {
        "channel_id": channel.id,
        "group_name": "[INC-1] DB",
        "owner_username": "operator",
        "continuous_sync_enabled": True,
        **overrides,
    }


def create_active_group(incident, channel, **overrides):
    values = {
        "incident": incident,
        "channel": channel,
        "channel_name_snapshot": channel.name,
        "member_id_type": "open_id",
        "group_name": "测试群",
        "external_chat_id": "oc_test",
        "status": IncidentIMGroup.Status.ACTIVE,
        "current_stage": IncidentIMGroup.Stage.COMPLETED,
        "idempotency_key": f"bklite-{uuid.uuid4().hex}",
        "created_by": "operator",
    }
    values.update(overrides)
    return IncidentIMGroup.objects.create(**values)
