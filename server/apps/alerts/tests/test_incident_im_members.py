import uuid

import pytest

from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.members import get_pending_members, reconcile_member_snapshots, resolve_incident_members
from apps.system_mgmt.models import IMNotificationChannel, IMNotificationSyncRun, IMNotificationUserMapping, IntegrationInstance, User


@pytest.fixture
def incident(db):
    return Incident.objects.create(
        incident_id=f"INC-{uuid.uuid4().hex}",
        level="warning",
        title="Incident IM 成员测试",
    )


@pytest.fixture
def channel(db):
    instance = IntegrationInstance.objects.create(
        name=f"feishu-{uuid.uuid4().hex}",
        provider_key="feishu",
        enabled=True,
        status="ready",
    )
    return IMNotificationChannel.objects.create(
        name=f"channel-{uuid.uuid4().hex}",
        integration_instance=instance,
        enabled=True,
        status="ready",
    )


@pytest.fixture
def users(db):
    return {
        username: User.objects.create(
            username=username,
            display_name=display_name,
            email=f"{username}@example.com",
            password="test-password",
        )
        for username, display_name in (("alice", "Alice"), ("bob", "Bob"), ("carol", "Carol"))
    }


@pytest.fixture
def mapping(channel, users):
    return IMNotificationUserMapping.objects.create(
        channel=channel,
        user=users["alice"],
        external_identity_key="open_id",
        external_identity_value="identity-alice",
        external_receive_key="open_id",
        external_display_name="Alice 外部显示名",
        external_snapshot={"user_id": "u_alice", "open_id": "ou_alice"},
    )


@pytest.fixture
def group(incident, channel):
    return IncidentIMGroup.objects.create(
        incident=incident,
        channel=channel,
        provider_key="feishu",
        channel_name_snapshot=channel.name,
        member_id_type="open_id",
        group_name=f"[INC-{incident.id}] 测试群",
        status=IncidentIMGroup.Status.ACTIVE,
        idempotency_key=f"bklite-{uuid.uuid4().hex}",
    )


@pytest.mark.django_db
def test_resolver_deduplicates_operator_and_collaborator_and_prefers_operator(incident, channel, mapping, users):
    incident.operator = ["alice"]
    incident.collaborators = ["alice", "bob"]
    incident.save(update_fields=["operator", "collaborators"])
    IMNotificationUserMapping.objects.create(
        channel=channel,
        user=users["bob"],
        external_identity_key="open_id",
        external_identity_value="identity-bob",
        external_receive_key="open_id",
        external_snapshot={"open_id": "ou_bob"},
    )

    members = resolve_incident_members(incident, channel)

    assert [(item.username, item.role) for item in members] == [
        ("alice", "operator"),
        ("bob", "collaborator"),
    ]


@pytest.mark.django_db
def test_resolver_resolves_all_members_in_three_queries(incident, channel, mapping, users, django_assert_num_queries):
    incident.operator = ["alice"]
    incident.collaborators = ["bob", "carol"]
    incident.save(update_fields=["operator", "collaborators"])
    for username in ("bob", "carol"):
        IMNotificationUserMapping.objects.create(
            channel=channel,
            user=users[username],
            external_identity_key="open_id",
            external_identity_value=f"identity-{username}",
            external_receive_key="open_id",
            external_snapshot={"open_id": f"ou_{username}"},
        )

    with django_assert_num_queries(3):
        members = resolve_incident_members(incident, channel)

    assert [item.username for item in members] == ["alice", "bob", "carol"]


@pytest.mark.django_db
def test_mapping_uses_mapping_receive_key_snapshot(incident, channel, mapping):
    incident.operator = ["alice"]
    incident.save(update_fields=["operator"])
    mapping.external_receive_key = "open_id"
    mapping.external_snapshot = {"open_id": "ou_alice", "user_id": "u_alice"}
    mapping.save()

    member = resolve_incident_members(incident, channel)[0]

    assert member.external_id_type == "open_id"
    assert member.external_id == "ou_alice"
    assert member.mapping_status == "mapped"


@pytest.mark.django_db
def test_resolver_marks_missing_receive_snapshot_as_unmapped(incident, channel, mapping):
    incident.operator = ["alice"]
    incident.save(update_fields=["operator"])
    mapping.external_snapshot = {"user_id": "u_alice"}
    mapping.save(update_fields=["external_snapshot"])

    member = resolve_incident_members(incident, channel)[0]

    assert member.mapping_status == "unmapped"
    assert member.error_code == "IM_USER_RECEIVE_ID_MISSING"
    assert member.error_message == "外部接收标识缺失"


@pytest.mark.django_db
def test_resolver_marks_latest_sync_conflict_without_exposing_identity(incident, channel, users):
    incident.operator = ["carol"]
    incident.save(update_fields=["operator"])
    IMNotificationSyncRun.objects.create(
        channel=channel,
        payload={"conflict_issues": [{"platform_user_ids": [users["carol"].id]}]},
    )

    member = resolve_incident_members(incident, channel)[0]

    assert member.mapping_status == "conflict"
    assert member.error_code == "IM_USER_MAPPING_CONFLICT"
    assert member.error_message == "用户映射存在冲突"


@pytest.mark.django_db
def test_reconcile_never_deletes_member_removed_from_incident(group):
    joined_member = IncidentIMMember.objects.create(
        group=group,
        username="former-operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        external_id="ou_former",
        external_id_type="open_id",
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )
    group.incident.operator = []
    group.incident.collaborators = []
    group.incident.save(update_fields=["operator", "collaborators"])

    reconcile_member_snapshots(group, group.incident)

    assert group.members.get(username=joined_member.username).sync_status == "joined"


@pytest.mark.django_db
def test_reconcile_creates_new_member_and_promotes_mapped_waiting_to_pending(group, mapping):
    group.incident.operator = ["alice"]
    group.incident.save(update_fields=["operator"])

    reconcile_member_snapshots(group, group.incident)

    member = group.members.get(username="alice")
    assert member.role == "operator"
    assert member.external_id == "ou_alice"
    assert member.sync_status == "pending"


@pytest.mark.django_db
def test_reconcile_keeps_member_waiting_when_mapping_receive_type_differs_from_group(group, mapping):
    group.incident.operator = ["alice"]
    group.incident.save(update_fields=["operator"])
    mapping.external_receive_key = "user_id"
    mapping.external_snapshot = {"user_id": "u_alice", "open_id": "ou_alice"}
    mapping.save(update_fields=["external_receive_key", "external_snapshot"])

    reconcile_member_snapshots(group, group.incident)

    member = group.members.get(username="alice")
    assert member.mapping_status == "unmapped"
    assert member.sync_status == "waiting"
    assert member.external_id == ""
    assert member.external_id_type == ""
    assert member.last_error_code == "IM_USER_RECEIVE_ID_MISSING"


@pytest.mark.django_db
def test_reconcile_joined_member_with_changed_external_identity_becomes_pending(group, mapping):
    group.incident.operator = ["alice"]
    group.incident.save(update_fields=["operator"])
    joined = IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.COLLABORATOR,
        external_id="ou_old",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
        last_error_code="old-error",
        last_error_message="old-message",
    )

    reconcile_member_snapshots(group, group.incident)

    joined.refresh_from_db()
    assert joined.role == "operator"
    assert joined.external_id == "ou_alice"
    assert joined.sync_status == "pending"
    assert joined.last_error_code == ""
    assert joined.last_error_message == ""


@pytest.mark.django_db
def test_reconcile_joined_member_with_unchanged_identity_stays_joined(group, mapping):
    group.incident.operator = ["alice"]
    group.incident.save(update_fields=["operator"])
    joined = IncidentIMMember.objects.create(
        group=group,
        username="alice",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_alice",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.JOINED,
    )

    reconcile_member_snapshots(group, group.incident)

    joined.refresh_from_db()
    assert joined.sync_status == IncidentIMMember.SyncStatus.JOINED


@pytest.mark.django_db
def test_get_pending_members_returns_only_pending_members(group):
    pending = IncidentIMMember.objects.create(
        group=group,
        username="pending",
        role=IncidentIMMember.Role.OPERATOR,
        sync_status=IncidentIMMember.SyncStatus.PENDING,
    )
    IncidentIMMember.objects.create(
        group=group,
        username="waiting",
        role=IncidentIMMember.Role.COLLABORATOR,
        sync_status=IncidentIMMember.SyncStatus.WAITING,
    )

    assert list(get_pending_members(group)) == [pending]
