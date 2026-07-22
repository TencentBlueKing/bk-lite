import uuid

import pytest

from apps.alerts.models import AlertOutbox, Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.constants.constants import IncidentStatus
from apps.base.models import User as AuthUser
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationUserMapping, IntegrationInstance, User as IMUser


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
    user = AuthUser.objects.create_user(
        username="operator",
        password="test-pass",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Team 1"}],
    )
    user.permission = {"alarm": {"Incidents-View", "Incidents-Edit"}}
    return user


@pytest.fixture
def collaborator(db):
    user = AuthUser.objects.create_user(
        username="collaborator",
        password="test-pass",
        domain="domain.com",
        group_list=[{"id": 1, "name": "Team 1"}],
    )
    user.permission = {"alarm": {"Incidents-View", "Incidents-Edit"}}
    return user


@pytest.fixture
def superuser(db):
    user = AuthUser.objects.create_user(
        username="superuser",
        password="test-pass",
        domain="domain.com",
        is_superuser=True,
    )
    return user


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
        name=f"channel-{uuid.uuid4().hex}",
        integration_instance=instance,
        enabled=True,
        status="ready",
        external_receive_field="open_id",
        team=[1],
    )


@pytest.fixture
def operator_mapping(channel):
    user = IMUser.objects.create(
        username="operator",
        display_name="Operator",
        email="operator@example.com",
        password="test-pass",
    )
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


@pytest.mark.django_db
def test_collaborator_can_read_group_but_cannot_load_options_or_create(api_client, collaborator, incident, channel):
    api_client.force_authenticate(collaborator)

    assert api_client.get(group_url(incident)).status_code == 200
    assert api_client.get(f"{group_url(incident)}options/").status_code == 403
    assert api_client.post(group_url(incident), create_payload(channel), format="json").status_code == 403


@pytest.mark.django_db
def test_superuser_not_in_operator_cannot_create_group(api_client, superuser, incident, channel):
    api_client.force_authenticate(superuser)

    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert response.status_code == 403
    assert response.json()["code"] == "IM_OPERATOR_REQUIRED"


@pytest.mark.django_db
def test_options_rejects_cross_team_channel(api_client, operator, incident, channel):
    channel.team = [2]
    channel.save(update_fields=["team"])
    api_client.force_authenticate(operator)

    response = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")

    assert response.status_code == 403
    assert response.json()["code"] == "IM_CHANNEL_FORBIDDEN"


@pytest.mark.django_db
def test_preview_marks_unmapped_collaborator_and_create_requires_mapped_operator(api_client, operator, incident, channel):
    api_client.force_authenticate(operator)

    preview = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")
    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert preview.status_code == 200
    assert {member["username"] for member in preview.json()["data"]["members"]} == {"operator", "collaborator"}
    assert response.status_code == 400
    assert response.json()["code"] == "IM_NO_MAPPED_OPERATOR"


@pytest.mark.django_db
def test_create_snapshots_partially_mapped_members_and_enqueues_outbox(
    api_client, operator, incident, channel, operator_mapping
):
    api_client.force_authenticate(operator)

    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert response.status_code == 202
    group = IncidentIMGroup.objects.get(incident=incident)
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.member_id_type == "open_id"
    assert set(group.members.values_list("username", flat=True)) == {"operator", "collaborator"}
    assert group.members.get(username="operator").mapping_status == IncidentIMMember.MappingStatus.MAPPED
    assert group.members.get(username="collaborator").mapping_status == IncidentIMMember.MappingStatus.UNMAPPED
    outbox = AlertOutbox.objects.get(idempotency_key=f"incident-im-group:{group.id}:create")
    assert outbox.kind == "incident_im_group.create"


@pytest.mark.django_db(transaction=True)
def test_duplicate_create_returns_conflict_and_one_binding(api_client, operator, incident, channel, operator_mapping):
    api_client.force_authenticate(operator)

    first = api_client.post(group_url(incident), create_payload(channel), format="json")
    second = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert first.status_code == 202
    assert second.status_code == 409
    assert second.json()["code"] == "IM_GROUP_ACTIVE_EXISTS"
    assert IncidentIMGroup.objects.filter(incident=incident).count() == 1


@pytest.mark.django_db
def test_closed_incident_cannot_create_group(api_client, operator, incident, channel, operator_mapping):
    incident.status = IncidentStatus.CLOSED
    incident.save(update_fields=["status"])
    api_client.force_authenticate(operator)

    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert response.status_code == 409


@pytest.mark.django_db
def test_collaborator_can_read_paginated_member_snapshots(api_client, collaborator, incident, channel, operator_mapping):
    group = IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="测试群",
        status=IncidentIMGroup.Status.ACTIVE,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    api_client.force_authenticate(collaborator)

    response = api_client.get(f"{group_url(incident)}members/?page=1&page_size=1")

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 1
    assert len(response.json()["data"]["items"]) == 1


@pytest.mark.django_db
def test_settings_require_operator_and_update_continuous_sync(api_client, operator, collaborator, incident, channel, operator_mapping):
    group = IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name="测试群",
        status=IncidentIMGroup.Status.ACTIVE,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )
    api_client.force_authenticate(collaborator)
    assert api_client.patch(group_url(incident), {"continuous_sync_enabled": False}, format="json").status_code == 403

    api_client.force_authenticate(operator)
    response = api_client.patch(group_url(incident), {"continuous_sync_enabled": False}, format="json")

    assert response.status_code == 200
    group.refresh_from_db()
    assert group.continuous_sync_enabled is False
    assert api_client.patch(f"{group_url(incident)}{group.id}/", {"continuous_sync_enabled": True}, format="json").status_code == 404
