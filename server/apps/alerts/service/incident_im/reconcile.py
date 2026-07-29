from django.db import transaction
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.constants import OUTBOX_ADD_MEMBERS, OUTBOX_CREATE, OUTBOX_RECONCILE, OUTBOX_SEND_SUMMARY
from apps.alerts.service.incident_im.errors import IncidentIMError
from apps.alerts.service.incident_im.members import get_desired_usernames, reconcile_member_snapshots
from apps.alerts.service.incident_im.observability import emit_incident_im_event
from apps.alerts.service.outbox import enqueue_outbox

SYNCABLE_GROUP_STATUSES = (IncidentIMGroup.Status.ACTIVE, IncidentIMGroup.Status.ACTIVE_PARTIAL)


def reconcile_incident_im_group(incident_id, force_delivery=False, resume_create=False):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None:
            emit_incident_im_event(
                "incident_im_reconcile",
                incident_id=incident_id,
                result="skipped",
                skip_reason="group_not_found",
            )
            return None

        terminal_status = _terminal_status_from_delivery_facts(group)
        retrying_exhausted_add = (
            force_delivery
            and group.external_chat_id
            and group.last_error_code == "IM_DELIVERY_EXHAUSTED"
        )
        if terminal_status is not None and not retrying_exhausted_add:
            if group.status != terminal_status:
                group.status = terminal_status
                group.save(update_fields=["status"])
            emit_incident_im_event(
                "incident_im_reconcile",
                group_id=str(group.id),
                incident_id=group.incident_id,
                result="skipped",
                skip_reason="terminal_delivery",
                status=group.status,
            )
            return group

        if force_delivery and not _can_deliver(group, force_delivery=True):
            emit_incident_im_event(
                "incident_im_reconcile",
                group_id=str(group.id),
                incident_id=group.incident_id,
                result="skipped",
                skip_reason="group_not_deliverable",
                status=group.status,
                pause_reason=group.pause_reason,
            )
            return group

        if resume_create and not group.external_chat_id:
            group.status = IncidentIMGroup.Status.PENDING_CREATE
            group.current_stage = IncidentIMGroup.Stage.QUEUED
            group.save(update_fields=["status", "current_stage"])
            enqueue_recovered_create(group)
            return group

        resolved_members = reconcile_member_snapshots(group, group.incident)
        desired_usernames = {member.username for member in resolved_members}
        if force_delivery:
            group.members.filter(
                username__in=desired_usernames, mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.FAILED
            ).exclude(external_id="").update(
                sync_status=IncidentIMMember.SyncStatus.PENDING, last_error_code="", last_error_message="", updated_at=timezone.now()
            )
        if (
            group.status == IncidentIMGroup.Status.ACTIVE
            and group.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        ):
            group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
            group.save(update_fields=["status"])
        if not _can_deliver(group, force_delivery=force_delivery, resume_create=resume_create):
            waiting_mapping_count = group.members.filter(
                username__in=desired_usernames,
                sync_status=IncidentIMMember.SyncStatus.WAITING,
            ).count()
            emit_incident_im_event(
                "incident_im_reconcile",
                group_id=str(group.id),
                incident_id=group.incident_id,
                result="skipped",
                skip_reason="group_not_deliverable",
                waiting_mapping_count=waiting_mapping_count,
                status=group.status,
                pause_reason=group.pause_reason,
            )
            return group

        pending = list(
            group.members.filter(
                username__in=desired_usernames, mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.PENDING
            )
            .exclude(external_id="")
            .order_by("pk")
        )
        if pending and not _has_unfinished_add_members(group.id):
            from apps.alerts.service.incident_im.delivery import enqueue_add_members_batch

            enqueue_add_members_batch(group, allow_failed_retry=force_delivery)
        elif not pending and group.current_stage in (IncidentIMGroup.Stage.ADDING_MEMBERS, IncidentIMGroup.Stage.SENDING_SUMMARY):
            _enqueue_recovered_summary(group)
        waiting_mapping_count = group.members.filter(
            username__in=desired_usernames,
            sync_status=IncidentIMMember.SyncStatus.WAITING,
        ).count()
        emit_incident_im_event(
            "incident_im_reconcile",
            group_id=str(group.id),
            incident_id=group.incident_id,
            result="scheduled" if pending else "complete",
            member_count=len(desired_usernames),
            pending_count=len(pending),
            waiting_mapping_count=waiting_mapping_count,
            status=group.status,
        )
        return group


def reconcile_incident_im_group_by_group_id(group_id, force_delivery=False):
    incident_id = IncidentIMGroup.objects.filter(pk=group_id, active_slot=1).values_list("incident_id", flat=True).first()
    if incident_id is None:
        return None
    return reconcile_incident_im_group(incident_id, force_delivery=force_delivery)


def retry_incident_im_member(*, incident_id, actor_username, username):
    from apps.alerts.service.incident_im.groups import IncidentIMGroupService

    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None:
            raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
        IncidentIMGroupService.require_operator_username(group.incident, actor_username)
        if not _can_deliver(group, force_delivery=True):
            raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不允许重试成员", 409)
        if username not in get_desired_usernames(group.incident):
            raise IncidentIMError("IM_MEMBER_NOT_RETRYABLE", "该用户已不属于当前 Incident", 409)

        member = group.members.select_for_update().filter(username=username).first()
        if (
            member is None
            or member.sync_status != IncidentIMMember.SyncStatus.FAILED
            or member.mapping_status != IncidentIMMember.MappingStatus.MAPPED
            or not member.external_id
        ):
            raise IncidentIMError("IM_MEMBER_NOT_RETRYABLE", "该成员当前不可重试", 409)

        member.sync_status = IncidentIMMember.SyncStatus.PENDING
        member.last_error_code = ""
        member.last_error_message = ""
        member.save(update_fields=["sync_status", "last_error_code", "last_error_message", "updated_at"])
        if not _has_unfinished_add_members(group.id):
            from apps.alerts.service.incident_im.delivery import enqueue_add_members_batch

            enqueue_add_members_batch(group, allow_failed_retry=True)
        return group


def pause_group_for_closed_incident(incident_id):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if (
            group is None
            or group.pause_reason == IncidentIMGroup.PauseReason.MANUAL
            or group.status
            not in (
                IncidentIMGroup.Status.PENDING_CREATE,
                IncidentIMGroup.Status.CREATING,
                IncidentIMGroup.Status.ACTIVE,
                IncidentIMGroup.Status.ACTIVE_PARTIAL,
            )
        ):
            return group
        group.resume_after_reopen = (
            group.status in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING)
            or group.current_stage == IncidentIMGroup.Stage.SENDING_SUMMARY
            or group.continuous_sync_enabled
        )
        group.status = IncidentIMGroup.Status.PAUSED
        group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
        group.save(update_fields=["resume_after_reopen", "status", "pause_reason"])
        emit_incident_im_event(
            "incident_im_lifecycle",
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation="pause",
            result="success",
            status=group.status,
            pause_reason=group.pause_reason,
        )
        return group


def resume_group_for_reopened_incident(incident_id):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None or group.status != IncidentIMGroup.Status.PAUSED or group.pause_reason != IncidentIMGroup.PauseReason.INCIDENT_CLOSED:
            return group

        terminal_status = _terminal_status_from_delivery_facts(group, allow_paused=True)
        if terminal_status is not None:
            group.status = terminal_status
            group.pause_reason = ""
            group.resume_after_reopen = False
            group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
            emit_incident_im_event(
                "incident_im_lifecycle",
                group_id=str(group.id),
                incident_id=group.incident_id,
                operation="resume",
                result="terminal",
                status=group.status,
            )
            return group

        should_resume = group.resume_after_reopen or group.current_stage == IncidentIMGroup.Stage.SENDING_SUMMARY
        if not group.external_chat_id:
            group.status = IncidentIMGroup.Status.PENDING_CREATE
            group.current_stage = IncidentIMGroup.Stage.QUEUED
            group.pause_reason = ""
            group.resume_after_reopen = False
            group.save(update_fields=["status", "current_stage", "pause_reason", "resume_after_reopen"])
            enqueue_outbox(
                OUTBOX_CREATE,
                {"group_id": str(group.id)},
                "incident-im-group:" f"{group.id}:create:reopen:" f"{group.incident.updated_at.isoformat(timespec='microseconds')}",
            )
            emit_incident_im_event(
                "incident_im_lifecycle",
                group_id=str(group.id),
                incident_id=group.incident_id,
                operation="resume",
                result="scheduled",
                status=group.status,
            )
            return group

        desired_usernames = get_desired_usernames(group.incident)
        has_member_gap = group.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL if has_member_gap else IncidentIMGroup.Status.ACTIVE
        group.pause_reason = ""
        group.resume_after_reopen = False
        group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
        if should_resume:
            enqueue_reconcile(group.incident, resume_create=True)
        emit_incident_im_event(
            "incident_im_lifecycle",
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation="resume",
            result="scheduled" if should_resume else "success",
            status=group.status,
        )
        return group


def enqueue_reconcile(incident, *, resume_create=False):
    updated_at = incident.updated_at.isoformat(timespec="microseconds")
    payload = {"incident_id": incident.pk}
    if resume_create:
        payload["resume_create"] = True
    return enqueue_outbox(OUTBOX_RECONCILE, payload, f"incident-im-group:{incident.pk}:reconcile:{updated_at}:{int(resume_create)}")


def _lock_active_group_for_incident(incident_id):
    return (
        IncidentIMGroup.objects.select_for_update()
        .select_related("incident", "channel", "channel__integration_instance")
        .filter(incident_id=incident_id, active_slot=1)
        .first()
    )


def _can_deliver(group, force_delivery, resume_create=False):
    return (
        group.status in SYNCABLE_GROUP_STATUSES
        and not group.pause_reason
        and group.incident.status in IncidentStatus.ACTIVATE_STATUS
        and (group.continuous_sync_enabled or force_delivery or resume_create)
    )


def _has_unfinished_add_members(group_id):
    return AlertOutbox.objects.filter(
        kind=OUTBOX_ADD_MEMBERS,
        payload__group_id=str(group_id),
        status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
    ).exists()


def _terminal_status_from_delivery_facts(group, *, allow_paused=False):
    if not allow_paused and (
        group.status == IncidentIMGroup.Status.PAUSED or group.pause_reason or group.incident.status not in IncidentStatus.ACTIVATE_STATUS
    ):
        return None
    if group.current_stage != IncidentIMGroup.Stage.COMPLETED or not group.last_error_code:
        return None
    if not group.external_chat_id:
        return IncidentIMGroup.Status.CREATE_FAILED
    if group.last_error_code == "provider.group_not_found":
        return IncidentIMGroup.Status.DEGRADED
    if group.last_error_code == "IM_DELIVERY_EXHAUSTED":
        return IncidentIMGroup.Status.ACTIVE_PARTIAL
    return None


def _enqueue_recovered_summary(group):
    payload = {"group_id": str(group.id)}
    if AlertOutbox.objects.filter(
        kind=OUTBOX_SEND_SUMMARY, payload=payload, status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING)
    ).exists():
        return
    consumed_id = (
        AlertOutbox.objects.filter(kind=OUTBOX_SEND_SUMMARY, payload=payload, status=AlertOutbox.Status.DELIVERED)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )
    idempotency_key = (
        f"incident-im-group:{group.id}:send-summary" if consumed_id is None else f"incident-im-group:{group.id}:send-summary:resume:{consumed_id}"
    )
    enqueue_outbox(OUTBOX_SEND_SUMMARY, payload, idempotency_key)


def enqueue_recovered_create(group):
    payload = {"group_id": str(group.id)}
    if AlertOutbox.objects.filter(
        kind=OUTBOX_CREATE, payload=payload, status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING)
    ).exists():
        return
    previous_id = AlertOutbox.objects.filter(kind=OUTBOX_CREATE, payload=payload).order_by("-pk").values_list("pk", flat=True).first()
    idempotency_key = f"incident-im-group:{group.id}:create" if previous_id is None else f"incident-im-group:{group.id}:create:resume:{previous_id}"
    enqueue_outbox(OUTBOX_CREATE, payload, idempotency_key)
