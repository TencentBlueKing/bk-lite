import pytest

from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.tests.incident_im_group_fixtures import create_active_group, group_url
from apps.system_mgmt.models import IMNotificationUserMapping
from apps.system_mgmt.models import User as IMUser

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_group_fixtures"]


def test_retry_failed_member_only_enqueues_selected_current_incident_member(api_client, operator, incident, channel, operator_mapping):
    collaborator_user = IMUser.objects.create(
        username="collaborator", display_name="Collaborator", email="collaborator@example.com", password="test-pass"
    )
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=collaborator_user,
        external_identity_key="open_id",
        external_identity_value="collaborator",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_collaborator"},
    )
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL)
    selected = IncidentIMMember.objects.create(
        group=group,
        username="collaborator",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_collaborator",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
        last_error_message="外部用户标识无效",
    )
    untouched = IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_operator",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="IM_MEMBER_INVALID",
        last_error_message="外部用户标识无效",
    )
    api_client.force_authenticate(operator)

    response = api_client.post(f"{group_url(incident)}retry/", {"username": "collaborator"}, format="json")

    assert response.status_code == 200
    selected.refresh_from_db()
    untouched.refresh_from_db()
    assert selected.sync_status == IncidentIMMember.SyncStatus.PENDING
    assert selected.last_error_code == ""
    assert untouched.sync_status == IncidentIMMember.SyncStatus.FAILED
    event = AlertOutbox.objects.get(
        kind="incident_im_group.add_members",
        payload__group_id=str(group.id),
    )
    assert event.status == AlertOutbox.Status.PENDING
    assert event.payload["member_pks"] == [selected.pk]


@pytest.mark.parametrize(
    ("username", "sync_status"), [("removed", IncidentIMMember.SyncStatus.FAILED), ("collaborator", IncidentIMMember.SyncStatus.JOINED)]
)
def test_retry_member_rejects_removed_or_non_failed_member_without_mutation(api_client, operator, incident, channel, username, sync_status):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL)
    member = IncidentIMMember.objects.create(
        group=group,
        username=username,
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id=f"ou_{username}",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=sync_status,
        last_error_code="IM_MEMBER_INVALID" if sync_status == IncidentIMMember.SyncStatus.FAILED else "",
    )
    api_client.force_authenticate(operator)

    response = api_client.post(f"{group_url(incident)}retry/", {"username": username}, format="json")

    assert response.status_code == 409
    assert response.json()["code"] == "IM_MEMBER_NOT_RETRYABLE"
    member.refresh_from_db()
    assert member.sync_status == sync_status
    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members", payload={"group_id": str(group.id)}).exists()
