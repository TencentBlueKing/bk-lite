import uuid
from datetime import datetime
from unittest.mock import patch

import pytest

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember, OperatorLog
from apps.alerts.service.incident_im.groups import IncidentIMGroupService
from apps.alerts.tests.incident_im_group_fixtures import create_active_group, create_payload, group_url
from apps.system_mgmt.models import IMNotificationUserMapping
from apps.system_mgmt.models import User as IMUser
from apps.system_mgmt.services.im_group_service import IMGroupRuntimeService

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
pytest_plugins = ["apps.alerts.tests.incident_im_group_fixtures"]


@pytest.mark.django_db
def test_collaborator_can_read_group_but_cannot_load_options_or_create(api_client, collaborator, incident, channel):
    api_client.force_authenticate(collaborator)

    assert api_client.get(group_url(incident)).status_code == 200
    options = api_client.get(f"{group_url(incident)}options/")
    assert options.status_code == 200
    assert options.json()["data"]["can_create"] is False
    assert options.json()["data"]["channels"] == []
    assert api_client.post(group_url(incident), create_payload(channel), format="json").status_code == 403


@pytest.mark.django_db
def test_options_read_only_operator_with_channel_id_returns_empty_safe_payload_without_sensitive_lookup(api_client, operator, incident, channel):
    operator.permission = {"alarm": {"Incidents-View"}}
    api_client.force_authenticate(operator)

    with patch.object(IMGroupRuntimeService, "list_ready_channels") as list_channels, patch.object(
        IncidentIMGroupService, "require_ready_channel"
    ) as require_channel, patch("apps.alerts.views.incident_im.resolve_incident_members") as resolve_members:
        response = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "can_create": False,
        "channels": [],
        "default_group_name": f"[{incident.incident_id}] {incident.title}",
        "members": [],
        "owner_candidates": [],
        "preferred_owner_username": None,
    }
    list_channels.assert_not_called()
    require_channel.assert_not_called()
    resolve_members.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("permissions", "expected"),
    (
        (
            {"Incidents-View"},
            {
                "can_manage": False,
                "can_retry": False,
                "can_pause": False,
                "can_resume": False,
                "can_unlink": False,
            },
        ),
        (
            {"Incidents-View", "Incidents-Edit"},
            {
                "can_manage": True,
                "can_retry": True,
                "can_pause": True,
                "can_resume": False,
                "can_unlink": True,
            },
        ),
    ),
)
def test_group_permissions_follow_operator_and_incident_edit_contract(
    api_client,
    operator,
    incident,
    channel,
    permissions,
    expected,
):
    create_active_group(incident, channel)
    operator.permission = {"alarm": permissions}
    api_client.force_authenticate(operator)

    response = api_client.get(group_url(incident))

    assert response.status_code == 200
    assert response.json()["data"]["permissions"] == expected


@pytest.mark.django_db
def test_collaborator_group_response_exposes_safe_ui_contract_without_guessing_chat_url(api_client, collaborator, incident, channel):
    group = create_active_group(
        incident,
        channel,
        status=IncidentIMGroup.Status.ACTIVE_PARTIAL,
        last_error_code="provider.permission_denied",
        last_error_message="raw payload app_secret=never-return-this",
    )
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="collaborator",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.UNMAPPED,
        sync_status=IncidentIMMember.SyncStatus.WAITING,
    )
    api_client.force_authenticate(collaborator)

    response = api_client.get(group_url(incident))

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["provider"] == "feishu"
    assert payload["external_chat_id"] == "oc_test"
    assert payload["open_chat_url"] is None
    assert payload["status_message"] == "1 人待映射"
    assert "never-return-this" not in response.content.decode()
    assert "app_secret" not in response.content.decode()


@pytest.mark.django_db
def test_group_summary_distinguishes_mapping_conflicts_from_unmapped_members(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.CONFLICT,
        sync_status=IncidentIMMember.SyncStatus.WAITING,
    )
    api_client.force_authenticate(collaborator)

    pure_conflict = api_client.get(group_url(incident))
    IncidentIMMember.objects.create(
        group=group,
        username="collaborator",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.UNMAPPED,
        sync_status=IncidentIMMember.SyncStatus.WAITING,
    )
    mixed = api_client.get(group_url(incident))

    assert pure_conflict.status_code == 200
    assert pure_conflict.json()["data"]["member_summary"]["conflict"] == 1
    assert pure_conflict.json()["data"]["member_summary"]["unmapped"] == 0
    assert pure_conflict.json()["data"]["status_message"] == "1 人映射冲突"
    assert mixed.json()["data"]["member_summary"]["conflict"] == 1
    assert mixed.json()["data"]["member_summary"]["unmapped"] == 1
    assert mixed.json()["data"]["status_message"] == "1 人映射冲突，1 人待映射"


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
def test_options_prefers_current_operator_when_mapped_even_if_not_first_candidate(api_client, operator, incident, channel, operator_mapping):
    backup = IMUser.objects.create(username="backup", display_name="Backup", email="backup@example.com", password="test-pass",)
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=backup,
        external_identity_key="open_id",
        external_identity_value="backup",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_backup"},
    )
    incident.operator = ["backup", "operator"]
    incident.save(update_fields=["operator"])
    api_client.force_authenticate(operator)

    response = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["can_create"] is True
    assert [candidate["username"] for candidate in payload["owner_candidates"]] == [
        "backup",
        "operator",
    ]
    assert payload["preferred_owner_username"] == "operator"


@pytest.mark.django_db
def test_options_falls_back_to_first_mapped_owner_candidate_or_null(api_client, operator, incident, channel):
    backup = IMUser.objects.create(username="backup", display_name="Backup", email="backup@example.com", password="test-pass",)
    mapping = IMNotificationUserMapping.objects.create(
        channel=channel,
        user=backup,
        external_identity_key="open_id",
        external_identity_value="backup",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_backup"},
    )
    incident.operator = ["operator", "backup"]
    incident.save(update_fields=["operator"])
    api_client.force_authenticate(operator)

    fallback = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")
    mapping.delete()
    no_candidate = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")

    assert fallback.status_code == 200
    assert fallback.json()["data"]["preferred_owner_username"] == "backup"
    assert no_candidate.json()["data"]["preferred_owner_username"] is None


@pytest.mark.django_db
def test_preview_marks_unmapped_collaborator_and_create_requires_mapped_operator(api_client, operator, incident, channel):
    api_client.force_authenticate(operator)

    preview = api_client.get(f"{group_url(incident)}options/?channel_id={channel.id}")
    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert preview.status_code == 200
    assert {member["username"] for member in preview.json()["data"]["members"]} == {
        "operator",
        "collaborator",
    }
    assert response.status_code == 400
    assert response.json()["code"] == "IM_NO_MAPPED_OPERATOR"


@pytest.mark.django_db
def test_create_snapshots_partially_mapped_members_and_enqueues_outbox(api_client, operator, incident, channel, operator_mapping):
    api_client.force_authenticate(operator)

    response = api_client.post(group_url(incident), create_payload(channel), format="json")

    assert response.status_code == 202
    group = IncidentIMGroup.objects.get(incident=incident)
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.member_id_type == "open_id"
    assert group.active_slot == 1
    assert group.idempotency_key == f"bklite-{group.id.hex}"
    assert group.external_owner_id == "ou_operator"
    assert set(group.members.values_list("username", flat=True)) == {
        "operator",
        "collaborator",
    }
    assert group.members.get(username="operator").mapping_status == IncidentIMMember.MappingStatus.MAPPED
    assert group.members.get(username="collaborator").mapping_status == IncidentIMMember.MappingStatus.UNMAPPED
    outbox = AlertOutbox.objects.get(idempotency_key=f"incident-im-group:{group.id}:create")
    assert outbox.kind == "incident_im_group.create"
    assert outbox.payload == {"group_id": str(group.id)}
    create_log = OperatorLog.objects.get(target_id=incident.incident_id, overview__contains="创建飞书群请求",)
    assert "成员 2 人" in create_log.overview
    assert "ou_operator" not in create_log.overview


@pytest.mark.django_db
@pytest.mark.parametrize("username_length", (33, 100))
def test_create_accepts_owner_username_up_to_im_mapping_user_model_limit(
    api_client,
    operator,
    incident,
    channel,
    username_length,
):
    owner_username = "a" * username_length
    operator.username = owner_username
    operator.save(update_fields=["username"])
    incident.operator = [owner_username]
    incident.save(update_fields=["operator"])
    mapped_user = IMUser.objects.create(
        username=owner_username,
        display_name="Long Username Operator",
        email="long-username@example.com",
        password="test-pass",
    )
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=mapped_user,
        external_identity_key="open_id",
        external_identity_value=owner_username,
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_long_username"},
    )
    api_client.force_authenticate(operator)

    response = api_client.post(
        group_url(incident),
        create_payload(channel, owner_username=owner_username),
        format="json",
    )

    assert response.status_code == 202
    assert IncidentIMGroup.objects.get(incident=incident).created_by == owner_username


@pytest.mark.django_db
def test_create_rejects_owner_username_above_im_mapping_user_model_limit(
    api_client,
    operator,
    incident,
    channel,
):
    owner_username = "a" * 101
    operator.username = owner_username
    operator.save(update_fields=["username"])
    incident.operator = [owner_username]
    incident.save(update_fields=["operator"])
    api_client.force_authenticate(operator)

    response = api_client.post(
        group_url(incident),
        create_payload(channel, owner_username=owner_username),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "40000"
    assert response.json()["message"].startswith("owner_username:")
    assert not IncidentIMGroup.objects.filter(incident=incident).exists()


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
    assert response.json() == {
        "result": False,
        "code": "IM_INCIDENT_NOT_ACTIVE",
        "message": "Incident 已关闭或已处理，无法创建协作群",
        "data": {"details": {}},
    }


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

    response = api_client.get(f"{group_url(incident)}members/?page=1&page_size=10")

    assert response.status_code == 200
    assert response.json()["data"]["count"] == 1
    assert len(response.json()["data"]["items"]) == 1


@pytest.mark.django_db
def test_members_default_sort_and_response_are_safe_for_read_only_users(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel)
    member_values = (
        ("joined", IncidentIMMember.MappingStatus.MAPPED, IncidentIMMember.SyncStatus.JOINED),
        ("pending", IncidentIMMember.MappingStatus.MAPPED, IncidentIMMember.SyncStatus.PENDING),
        ("adding", IncidentIMMember.MappingStatus.MAPPED, IncidentIMMember.SyncStatus.ADDING),
        ("unmapped", IncidentIMMember.MappingStatus.UNMAPPED, IncidentIMMember.SyncStatus.WAITING),
        ("conflict", IncidentIMMember.MappingStatus.CONFLICT, IncidentIMMember.SyncStatus.WAITING),
        ("failed", IncidentIMMember.MappingStatus.MAPPED, IncidentIMMember.SyncStatus.FAILED),
    )
    for username, mapping_status, sync_status in member_values:
        IncidentIMMember.objects.create(
            group=group,
            username=username,
            role=IncidentIMMember.Role.COLLABORATOR,
            mapping_status=mapping_status,
            sync_status=sync_status,
            external_id=f"ou_secret_{username}",
        )
    api_client.force_authenticate(collaborator)

    response = api_client.get(f"{group_url(incident)}members/?filter=all")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["count"] == 6
    assert [item["username"] for item in payload["items"]] == [
        "failed",
        "conflict",
        "unmapped",
        "adding",
        "pending",
        "joined",
    ]
    assert all(datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00")) for item in payload["items"])
    assert "external_id" not in payload["items"][0]
    assert "ou_secret" not in response.content.decode()


@pytest.mark.django_db
def test_members_response_maps_internal_error_code_to_safe_message(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
        last_error_code="provider.unrecognized_error",
        last_error_message="raw payload app_secret=never-return-this",
    )
    api_client.force_authenticate(collaborator)

    response = api_client.get(f"{group_url(incident)}members/?filter=pending")

    assert response.status_code == 200
    member = response.json()["data"]["items"][0]
    assert member["error_code"] == "provider.unrecognized_error"
    assert member["error_message"] == "加入失败，请重试或联系管理员"
    assert "never-return-this" not in response.content.decode()
    assert "app_secret" not in response.content.decode()


@pytest.mark.django_db
def test_members_filters_pending_and_joined_and_defaults_to_twenty(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel)
    for index in range(21):
        IncidentIMMember.objects.create(
            group=group,
            username=f"joined-{index:02d}",
            role=IncidentIMMember.Role.COLLABORATOR,
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
            sync_status=IncidentIMMember.SyncStatus.JOINED,
        )
    pending_statuses = (
        IncidentIMMember.SyncStatus.WAITING,
        IncidentIMMember.SyncStatus.PENDING,
        IncidentIMMember.SyncStatus.ADDING,
        IncidentIMMember.SyncStatus.FAILED,
    )
    pending_usernames = []
    for sync_status in pending_statuses:
        username = f"pending-{sync_status}"
        pending_usernames.append(username)
        IncidentIMMember.objects.create(
            group=group,
            username=username,
            role=IncidentIMMember.Role.COLLABORATOR,
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
            sync_status=sync_status,
        )
    incident.collaborators = pending_usernames
    incident.save(update_fields=["collaborators"])
    api_client.force_authenticate(collaborator)

    default_page = api_client.get(f"{group_url(incident)}members/?filter=all")
    pending = api_client.get(f"{group_url(incident)}members/?filter=pending&page_size=10")
    joined = api_client.get(f"{group_url(incident)}members/?filter=joined&page_size=50")

    assert default_page.status_code == 200
    assert default_page.json()["data"]["count"] == 25
    assert len(default_page.json()["data"]["items"]) == 20
    assert {item["sync_status"] for item in pending.json()["data"]["items"]} == {
        IncidentIMMember.SyncStatus.WAITING,
        IncidentIMMember.SyncStatus.PENDING,
        IncidentIMMember.SyncStatus.ADDING,
        IncidentIMMember.SyncStatus.FAILED,
    }
    assert joined.json()["data"]["count"] == 21
    assert {item["sync_status"] for item in joined.json()["data"]["items"]} == {IncidentIMMember.SyncStatus.JOINED}


@pytest.mark.django_db
def test_group_summary_and_pending_filter_exclude_removed_non_joined_members(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="removed-pending",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="removed-joined",
        role=IncidentIMMember.Role.COLLABORATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    api_client.force_authenticate(collaborator)

    group_response = api_client.get(group_url(incident))
    pending = api_client.get(f"{group_url(incident)}members/?filter=pending")
    joined = api_client.get(f"{group_url(incident)}members/?filter=joined")

    assert group_response.status_code == 200
    summary = group_response.json()["data"]["member_summary"]
    assert summary["total"] == 2
    assert summary["joined"] == 1
    assert summary["pending"] == 1
    assert group_response.json()["data"]["status_message"] == "1 人待同步"
    assert [item["username"] for item in pending.json()["data"]["items"]] == ["operator"]
    assert [item["username"] for item in joined.json()["data"]["items"]] == ["removed-joined"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "error_code"),
    (
        ("filter=unknown", "IM_MEMBER_FILTER_INVALID"),
        ("page_size=1", "IM_MEMBER_PAGE_SIZE_INVALID"),
        ("page_size=0", "IM_MEMBER_PAGE_SIZE_INVALID"),
        ("page_size=101", "IM_MEMBER_PAGE_SIZE_INVALID"),
        ("page_size=abc", "IM_MEMBER_PAGE_SIZE_INVALID"),
    ),
)
def test_members_reject_invalid_filter_and_page_size(api_client, collaborator, incident, query, error_code):
    api_client.force_authenticate(collaborator)

    response = api_client.get(f"{group_url(incident)}members/?{query}")

    assert response.status_code == 400
    assert response.json()["code"] == error_code
