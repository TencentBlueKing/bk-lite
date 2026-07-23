import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from unittest.mock import Mock, patch

import pytest
from django.db import (
    IntegrityError,
    OperationalError,
    close_old_connections,
    connections,
    transaction,
)

from apps.alerts.models import (
    AlertOutbox,
    Incident,
    IncidentIMGroup,
    IncidentIMMember,
    OperatorLog,
)
from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.service.incident_im.errors import IncidentIMError
from apps.alerts.service.incident_im.groups import IncidentIMGroupService
from apps.base.models import User as AuthUser
from apps.system_mgmt.models import (
    IMNotificationChannel,
    IMNotificationUserMapping,
    IntegrationInstance,
    User as IMUser,
)


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
    user = AuthUser.objects.create_user(username="superuser", password="test-pass", domain="domain.com", is_superuser=True,)
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
    assert api_client.patch(f"{group_url(incident)}{group.id}/", {"continuous_sync_enabled": True}, format="json",).status_code == 404


@pytest.mark.django_db
def test_enabling_continuous_sync_reconciles_and_audits_but_disabling_only_changes_config(api_client, operator, incident, channel, operator_mapping):
    group = create_active_group(incident, channel, continuous_sync_enabled=False,)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        mapping_status=IncidentIMMember.MappingStatus.UNMAPPED,
        sync_status=IncidentIMMember.SyncStatus.WAITING,
    )
    api_client.force_authenticate(operator)

    disabled = api_client.patch(group_url(incident), {"continuous_sync_enabled": False}, format="json",)
    assert not AlertOutbox.objects.filter(kind="incident_im_group.add_members").exists()
    enabled = api_client.patch(group_url(incident), {"continuous_sync_enabled": True}, format="json",)

    assert disabled.status_code == 200
    assert enabled.status_code == 200
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members", payload={"group_id": str(group.id)},).count() == 1
    group.refresh_from_db()
    assert group.continuous_sync_enabled is True
    log = OperatorLog.objects.filter(target_type="incident", target_id=incident.incident_id, overview__contains="持续同步",).latest("id")
    assert str(group.id) in (log.operator_object or "")
    assert "oc_test" not in (log.overview or "")


@pytest.mark.django_db
def test_pause_and_resume_are_operator_only_audited_and_resume_create_flow(api_client, operator, collaborator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL, current_stage=IncidentIMGroup.Stage.SENDING_SUMMARY,)
    pause_url = f"{group_url(incident)}pause/"
    resume_url = f"{group_url(incident)}resume/"

    api_client.force_authenticate(collaborator)
    assert api_client.post(pause_url).status_code == 403

    api_client.force_authenticate(operator)
    paused = api_client.post(pause_url)
    group.refresh_from_db()
    assert paused.status_code == 200
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.MANUAL

    resumed = api_client.post(resume_url)

    assert resumed.status_code == 200
    assert AlertOutbox.objects.filter(kind="incident_im_group.send_summary", payload={"group_id": str(group.id)},).count() == 1
    group.refresh_from_db()
    assert group.pause_reason == ""
    assert group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL
    assert OperatorLog.objects.filter(target_id=incident.incident_id, overview__contains="暂停飞书群同步",).exists()
    assert OperatorLog.objects.filter(target_id=incident.incident_id, overview__contains="恢复飞书群同步",).exists()


@pytest.mark.django_db
def test_pause_and_resume_reject_invalid_states_with_stable_code(api_client, operator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.CREATE_FAILED,)
    api_client.force_authenticate(operator)

    pause_response = api_client.post(f"{group_url(incident)}pause/")
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    group.save(update_fields=["status", "pause_reason"])
    resume_response = api_client.post(f"{group_url(incident)}resume/")

    assert pause_response.status_code == 409
    assert pause_response.json()["code"] == "IM_GROUP_STATE_INVALID"
    assert resume_response.status_code == 409
    assert resume_response.json()["code"] == "IM_GROUP_STATE_INVALID"


@pytest.mark.django_db
def test_closed_incident_cannot_manual_resume(api_client, operator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.PAUSED, pause_reason=IncidentIMGroup.PauseReason.MANUAL,)
    incident.status = IncidentStatus.CLOSED
    incident.save(update_fields=["status"])
    api_client.force_authenticate(operator)

    response = api_client.post(f"{group_url(incident)}resume/")

    assert response.status_code == 409
    assert response.json()["code"] == "IM_INCIDENT_NOT_ACTIVE"
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.MANUAL


@pytest.mark.django_db
def test_retry_degraded_rechecks_external_group_without_recreating(api_client, operator, incident, channel):
    from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.DEGRADED, last_error_code="provider.group_not_found",)
    api_client.force_authenticate(operator)
    missing = CapabilityExecutionResult.failed_result("not found", code="provider.group_not_found",)

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", return_value=missing,) as execute:
        response = api_client.post(f"{group_url(incident)}retry/")

    assert response.status_code == 200
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.DEGRADED
    assert [call.kwargs["operation"] for call in execute.call_args_list] == ["get_group"]
    assert OperatorLog.objects.filter(target_id=incident.incident_id, overview__contains="重试飞书群",).exists()


@pytest.mark.django_db
def test_retry_active_partial_uses_manual_force_reconcile(api_client, operator, incident, channel, operator_mapping):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.ACTIVE_PARTIAL,)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_operator",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )
    api_client.force_authenticate(operator)

    response = api_client.post(f"{group_url(incident)}retry/")

    assert response.status_code == 200
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members", payload={"group_id": str(group.id)},).count() == 1


@pytest.mark.django_db
def test_retry_create_failed_requeues_create_without_direct_provider_call(api_client, operator, incident, channel):
    group = create_active_group(
        incident, channel, external_chat_id="", status=IncidentIMGroup.Status.CREATE_FAILED, last_error_code="provider.permission_denied",
    )
    api_client.force_authenticate(operator)

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute") as execute:
        response = api_client.post(f"{group_url(incident)}retry/")

    assert response.status_code == 200
    execute.assert_not_called()
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PENDING_CREATE
    assert group.current_stage == IncidentIMGroup.Stage.QUEUED
    assert AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)},).count() == 1


@pytest.mark.django_db
def test_retry_create_failed_rolls_back_state_when_outbox_enqueue_fails(api_client, operator, incident, channel):
    group = create_active_group(
        incident, channel, external_chat_id="", status=IncidentIMGroup.Status.CREATE_FAILED, last_error_code="provider.permission_denied",
    )
    api_client.force_authenticate(operator)

    with patch(
        "apps.alerts.service.incident_im.reconcile.enqueue_outbox", side_effect=RuntimeError("outbox unavailable"),
    ):
        response = api_client.post(f"{group_url(incident)}retry/")

    assert response.status_code == 500
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.CREATE_FAILED
    assert group.last_error_code == "provider.permission_denied"
    assert not AlertOutbox.objects.filter(kind="incident_im_group.create", payload={"group_id": str(group.id)},).exists()


@pytest.mark.django_db
def test_retry_degraded_existing_group_rechecks_then_force_reconciles(api_client, operator, incident, channel, operator_mapping):
    from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.DEGRADED,)
    IncidentIMMember.objects.create(
        group=group,
        username="operator",
        role=IncidentIMMember.Role.OPERATOR,
        external_id="ou_operator",
        external_id_type="open_id",
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        sync_status=IncidentIMMember.SyncStatus.FAILED,
    )
    api_client.force_authenticate(operator)

    with patch(
        "apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute",
        return_value=CapabilityExecutionResult.success_result("exists", payload={"chat_id": "oc_test"},),
    ) as execute:
        response = api_client.post(f"{group_url(incident)}retry/")

    assert response.status_code == 200
    assert execute.call_args.kwargs["operation"] == "get_group"
    assert AlertOutbox.objects.filter(kind="incident_im_group.add_members", payload={"group_id": str(group.id)},).count() == 1


@pytest.mark.django_db
def test_degraded_retry_does_not_mutate_replacement_binding(operator, incident, channel):
    old_group = create_active_group(incident, channel, status=IncidentIMGroup.Status.DEGRADED,)

    def replace_binding(*args, **kwargs):
        old_group.status = IncidentIMGroup.Status.UNLINKED
        old_group.save(update_fields=["status"])
        create_active_group(
            incident, channel, status=IncidentIMGroup.Status.DEGRADED, group_name="replacement",
        )
        from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

        return CapabilityExecutionResult.success_result("exists")

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", side_effect=replace_binding,), pytest.raises(
        IncidentIMError
    ) as error:
        IncidentIMGroupService.retry_degraded(
            incident_id=incident.id, actor_username=operator.username,
        )

    assert error.value.code == "IM_GROUP_STATE_INVALID"
    assert IncidentIMGroup.objects.get(incident=incident, active_slot=1,).status == IncidentIMGroup.Status.DEGRADED


@pytest.mark.django_db
def test_degraded_retry_does_not_reactivate_group_when_incident_closes(operator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.DEGRADED,)

    def close_incident(*args, **kwargs):
        incident.status = IncidentStatus.CLOSED
        incident.save(update_fields=["status"])
        from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

        return CapabilityExecutionResult.success_result("exists")

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute", side_effect=close_incident,), pytest.raises(
        IncidentIMError
    ) as error:
        IncidentIMGroupService.retry_degraded(
            incident_id=incident.id, actor_username=operator.username,
        )

    assert error.value.code == "IM_INCIDENT_NOT_ACTIVE"
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.DEGRADED


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("operation", "status", "pause_reason", "external_chat_id"),
    [
        ("set_continuous_sync", IncidentIMGroup.Status.ACTIVE, "", "oc_test"),
        ("pause", IncidentIMGroup.Status.ACTIVE, "", "oc_test"),
        ("resume", IncidentIMGroup.Status.PAUSED, IncidentIMGroup.PauseReason.MANUAL, "oc_test",),
        ("prepare_create_retry", IncidentIMGroup.Status.CREATE_FAILED, "", ""),
        ("retry_degraded", IncidentIMGroup.Status.DEGRADED, "", "oc_test"),
        ("unlink", IncidentIMGroup.Status.ACTIVE, "", "oc_test"),
    ],
)
def test_service_rechecks_operator_under_lock(operator, incident, channel, operation, status, pause_reason, external_chat_id):
    group = create_active_group(incident, channel, status=status, pause_reason=pause_reason, external_chat_id=external_chat_id,)
    incident.operator = ["replacement-operator"]
    incident.save(update_fields=["operator"])
    kwargs = {"incident_id": incident.id, "actor_username": operator.username}
    if operation == "set_continuous_sync":
        kwargs["enabled"] = False
    elif operation == "unlink":
        kwargs["group_name"] = group.group_name

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute"), pytest.raises(IncidentIMError) as error:
        getattr(IncidentIMGroupService, operation)(**kwargs)

    assert error.value.code == "IM_OPERATOR_REQUIRED"


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["retry", "pause", "resume"])
def test_non_operator_cannot_execute_group_management_actions(api_client, collaborator, incident, channel, action):
    create_active_group(incident, channel)
    api_client.force_authenticate(collaborator)

    response = api_client.post(f"{group_url(incident)}{action}/")

    assert response.status_code == 403
    assert response.json()["code"] == "IM_OPERATOR_REQUIRED"


@pytest.mark.django_db
def test_non_operator_cannot_unlink_group(api_client, collaborator, incident, channel):
    group = create_active_group(incident, channel)
    api_client.force_authenticate(collaborator)

    response = api_client.delete(group_url(incident), {"group_name": group.group_name}, format="json",)

    assert response.status_code == 403
    assert response.json()["code"] == "IM_OPERATOR_REQUIRED"


@pytest.mark.django_db
def test_unlink_rejects_busy_and_requires_exact_group_name(api_client, operator, incident, channel):
    group = create_active_group(incident, channel, status=IncidentIMGroup.Status.CREATING, current_stage=IncidentIMGroup.Stage.CREATING_CHAT,)
    api_client.force_authenticate(operator)

    creating = api_client.delete(group_url(incident), {"group_name": group.group_name}, format="json",)
    group.status = IncidentIMGroup.Status.ACTIVE
    group.current_stage = IncidentIMGroup.Stage.COMPLETED
    group.save(update_fields=["status", "current_stage"])
    mismatch = api_client.delete(group_url(incident), {"group_name": "wrong"}, format="json",)
    member = IncidentIMMember.objects.create(
        group=group, username="operator", role=IncidentIMMember.Role.OPERATOR, sync_status=IncidentIMMember.SyncStatus.ADDING,
    )
    adding = api_client.delete(group_url(incident), {"group_name": group.group_name}, format="json",)
    member.delete()
    whitespace = api_client.delete(group_url(incident), {"group_name": f" {group.group_name} "}, format="json",)

    assert creating.status_code == 409
    assert creating.json()["code"] == "IM_GROUP_BUSY"
    assert mismatch.status_code == 400
    assert mismatch.json()["code"] == "IM_GROUP_NAME_MISMATCH"
    assert adding.status_code == 409
    assert adding.json()["code"] == "IM_GROUP_BUSY"
    assert whitespace.status_code == 400
    assert whitespace.json()["code"] == "IM_GROUP_NAME_MISMATCH"


@pytest.mark.django_db
def test_unlink_is_local_atomic_and_allows_a_new_binding(api_client, operator, incident, channel):
    group = create_active_group(incident, channel)
    api_client.force_authenticate(operator)

    with patch("apps.alerts.service.incident_im.groups.IMGroupRuntimeService.execute") as execute:
        response = api_client.delete(group_url(incident), {"group_name": group.group_name}, format="json",)

    # 全局响应 wrapper 会把空的 204 规范化为统一 200 envelope。
    assert response.status_code == 200
    execute.assert_not_called()
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.UNLINKED
    assert group.active_slot is None
    assert group.unlinked_by == "operator"
    assert group.external_chat_id == "oc_test"
    replacement = create_active_group(incident, channel, group_name="replacement",)
    assert replacement.active_slot == 1
    log = OperatorLog.objects.get(target_id=incident.incident_id, overview__contains="解绑飞书群",)
    assert "oc_test" not in (log.overview or "")


@pytest.mark.django_db
def test_audit_failure_does_not_rollback_pause(api_client, operator, incident, channel):
    group = create_active_group(incident, channel)
    api_client.force_authenticate(operator)

    with patch(
        "apps.alerts.service.incident_im.groups.record_operator_log_deferred_mirror", side_effect=IntegrityError("audit unavailable"),
    ):
        response = api_client.post(f"{group_url(incident)}pause/")

    assert response.status_code == 200
    group.refresh_from_db()
    assert group.status == IncidentIMGroup.Status.PAUSED
    assert group.pause_reason == IncidentIMGroup.PauseReason.MANUAL


@pytest.mark.django_db(transaction=True)
def test_audit_mirror_runs_only_after_business_commit(incident, channel):
    from apps.alerts.service.incident_im.groups import record_group_audit

    group = create_active_group(incident, channel)
    with patch("apps.alerts.utils.operator_log._mirror") as mirror:
        with transaction.atomic():
            record_group_audit(group, "operator", "暂停飞书群同步")
            mirror.assert_not_called()
        mirror.assert_called_once()


@pytest.mark.django_db(transaction=True)
def test_rolled_back_business_does_not_mirror_audit(incident, channel):
    from apps.alerts.service.incident_im.groups import record_group_audit

    group = create_active_group(incident, channel)
    with patch("apps.alerts.utils.operator_log._mirror") as mirror:
        with pytest.raises(RuntimeError, match="rollback"):
            with transaction.atomic():
                record_group_audit(group, "operator", "暂停飞书群同步")
                raise RuntimeError("rollback")

    mirror.assert_not_called()
    assert not OperatorLog.objects.filter(target_id=incident.incident_id, overview__contains="暂停飞书群同步",).exists()


@pytest.mark.django_db
def test_http_options_returns_metadata_without_operator_or_preview_logic(api_client, collaborator, incident):
    api_client.force_authenticate(collaborator)

    group_response = api_client.options(group_url(incident))
    members_response = api_client.options(f"{group_url(incident)}members/")

    assert group_response.status_code == 200
    assert members_response.status_code == 200
    assert "name" in group_response.json()["data"]
    assert "name" in members_response.json()["data"]


@pytest.mark.django_db(transaction=True)
def test_sqlite_independent_connections_translate_busy_loser_after_active_winner(operator, incident, channel, operator_mapping, monkeypatch):
    database_vendor = connections["default"].vendor
    if database_vendor != "sqlite":
        pytest.skip(f"SQLite 锁竞争合同不适用于 {database_vendor}")

    from apps.alerts.service.incident_im import groups

    barrier = Barrier(2)
    worker_state = local()
    original_resolve = groups.resolve_incident_members

    def synchronized_resolve(*args, **kwargs):
        if not getattr(worker_state, "synchronized", False):
            worker_state.synchronized = True
            barrier.wait(timeout=10)
        return original_resolve(*args, **kwargs)

    monkeypatch.setattr(groups, "resolve_incident_members", synchronized_resolve)

    def create_from_independent_connection():
        close_old_connections()
        try:
            actor = AuthUser.objects.get(pk=operator.pk)
            group = groups.IncidentIMGroupService.create(
                incident_id=incident.id,
                actor=actor,
                channel_id=channel.id,
                group_name="并发测试群",
                owner_username="operator",
                continuous_sync_enabled=True,
            )
            return ("created", str(group.id), "")
        except Exception as exc:
            return (type(exc).__name__, getattr(exc, "code", ""), str(exc))
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = [future.result(timeout=20) for future in [executor.submit(create_from_independent_connection) for _ in range(2)]]

    assert sorted(outcome[0] for outcome in outcomes) == ["IncidentIMError", "created",], outcomes
    assert {outcome[1] for outcome in outcomes if outcome[0] == "IncidentIMError"} == {"IM_GROUP_ACTIVE_EXISTS"}
    assert IncidentIMGroup.objects.filter(incident=incident, active_slot=1).count() == 1


@pytest.mark.django_db
def test_sqlite_lock_retries_entire_create_transaction_after_no_winner(monkeypatch):
    from apps.alerts.service.incident_im import groups

    created_group = Mock()
    lock_error = OperationalError("database is locked")
    monkeypatch.setattr(groups.IncidentIMGroupService, "_is_sqlite_lock_error", lambda exc: True)
    monkeypatch.setattr(groups.IncidentIMGroupService, "_has_active_group", lambda incident_id: False)

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=[lock_error, created_group],) as create_once, patch(
        "apps.alerts.service.incident_im.groups.sleep"
    ) as sleep_mock:
        result = groups.IncidentIMGroupService.create(
            incident_id=1, actor=Mock(), channel_id=1, group_name="重试测试群", owner_username="operator", continuous_sync_enabled=True,
        )

    assert result is created_group
    assert create_once.call_count == 2
    sleep_mock.assert_called_once_with(groups.IncidentIMGroupService.SQLITE_LOCK_RETRY_DELAYS[0])


@pytest.mark.django_db
def test_sqlite_lock_reraises_last_error_after_retry_budget_exhausted(monkeypatch):
    from apps.alerts.service.incident_im import groups

    lock_errors = [OperationalError("database is locked") for _ in range(len(groups.IncidentIMGroupService.SQLITE_LOCK_RETRY_DELAYS) + 1)]
    monkeypatch.setattr(groups.IncidentIMGroupService, "_is_sqlite_lock_error", lambda exc: True)
    monkeypatch.setattr(groups.IncidentIMGroupService, "_has_active_group", lambda incident_id: False)

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=lock_errors) as create_once:
        with pytest.raises(OperationalError) as raised:
            groups.IncidentIMGroupService.create(
                incident_id=1, actor=Mock(), channel_id=1, group_name="重试耗尽测试群", owner_username="operator", continuous_sync_enabled=True,
            )

    assert raised.value is lock_errors[-1]
    assert create_once.call_count == len(lock_errors)


@pytest.mark.django_db
def test_non_sqlite_lock_operational_error_is_reraised_without_retry(monkeypatch):
    from apps.alerts.service.incident_im import groups

    lock_error = OperationalError("database is locked")
    monkeypatch.setattr(groups.connection, "vendor", "postgresql")

    with patch.object(groups.IncidentIMGroupService, "_create_once", side_effect=lock_error) as create_once:
        with pytest.raises(OperationalError) as raised:
            groups.IncidentIMGroupService.create(
                incident_id=1, actor=Mock(), channel_id=1, group_name="非 SQLite 测试群", owner_username="operator", continuous_sync_enabled=True,
            )

    assert raised.value is lock_error
    assert create_once.call_count == 1


@pytest.mark.django_db
@pytest.mark.parametrize("failure_target", ["bulk_create", "enqueue_outbox"])
def test_non_group_integrity_error_is_not_translated_to_active_conflict(operator, incident, channel, operator_mapping, failure_target):
    from apps.alerts.service.incident_im import groups

    target = (
        "apps.alerts.models.IncidentIMMember.objects.bulk_create"
        if failure_target == "bulk_create"
        else "apps.alerts.service.incident_im.groups.enqueue_outbox"
    )
    with patch(target, side_effect=IntegrityError("unrelated constraint")):
        with pytest.raises(IntegrityError):
            groups.IncidentIMGroupService.create(
                incident_id=incident.id,
                actor=operator,
                channel_id=channel.id,
                group_name="约束异常测试群",
                owner_username="operator",
                continuous_sync_enabled=True,
            )

    assert not IncidentIMGroup.objects.filter(incident=incident, active_slot=1).exists()
