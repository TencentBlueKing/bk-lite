import hashlib

from django.db import transaction
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.members import (
    get_desired_usernames,
    reconcile_member_snapshots,
)
from apps.alerts.service.outbox import enqueue_outbox


OUTBOX_ADD_MEMBERS = "incident_im_group.add_members"
OUTBOX_CREATE = "incident_im_group.create"
OUTBOX_RECONCILE = "incident_im_group.reconcile"
OUTBOX_SEND_SUMMARY = "incident_im_group.send_summary"
SYNCABLE_GROUP_STATUSES = (
    IncidentIMGroup.Status.ACTIVE,
    IncidentIMGroup.Status.ACTIVE_PARTIAL,
)


def reconcile_incident_im_group(incident_id, force_delivery=False, resume_create=False):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None:
            return None

        terminal_status = _terminal_status_from_delivery_facts(group)
        if terminal_status is not None:
            if group.status != terminal_status:
                group.status = terminal_status
                group.save(update_fields=["status"])
            return group

        if force_delivery and not _can_deliver(group, force_delivery=True):
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
                username__in=desired_usernames, mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.FAILED,
            ).exclude(external_id="").update(
                sync_status=IncidentIMMember.SyncStatus.PENDING, last_error_code="", last_error_message="", updated_at=timezone.now(),
            )
        if (
            group.status == IncidentIMGroup.Status.ACTIVE
            and group.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        ):
            group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
            group.save(update_fields=["status"])
        if not _can_deliver(group, force_delivery=force_delivery, resume_create=resume_create,):
            return group

        pending = list(
            group.members.filter(
                username__in=desired_usernames, mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            .exclude(external_id="")
            .order_by("pk")
        )
        if pending and not _has_unfinished_add_members(group.id):
            signature = "\0".join(f"{member.pk}:{member.updated_at.isoformat(timespec='microseconds')}" for member in pending)
            digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
            enqueue_outbox(
                OUTBOX_ADD_MEMBERS, {"group_id": str(group.id)}, f"incident-im-group:{group.id}:add-members:{digest}",
            )
        elif not pending and group.current_stage in (IncidentIMGroup.Stage.ADDING_MEMBERS, IncidentIMGroup.Stage.SENDING_SUMMARY,):
            _enqueue_recovered_summary(group)
        return group


def reconcile_incident_im_group_by_group_id(group_id, force_delivery=False):
    incident_id = IncidentIMGroup.objects.filter(pk=group_id, active_slot=1).values_list("incident_id", flat=True).first()
    if incident_id is None:
        return None
    return reconcile_incident_im_group(incident_id, force_delivery=force_delivery)


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
            group.status in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING,)
            or group.current_stage == IncidentIMGroup.Stage.SENDING_SUMMARY
            or group.continuous_sync_enabled
        )
        group.status = IncidentIMGroup.Status.PAUSED
        group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
        group.save(update_fields=["resume_after_reopen", "status", "pause_reason"])
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
            return group

        should_resume = group.resume_after_reopen or group.current_stage == IncidentIMGroup.Stage.SENDING_SUMMARY
        if not group.external_chat_id:
            group.status = IncidentIMGroup.Status.PENDING_CREATE
            group.current_stage = IncidentIMGroup.Stage.QUEUED
            group.pause_reason = ""
            group.resume_after_reopen = False
            group.save(
                update_fields=["status", "current_stage", "pause_reason", "resume_after_reopen",]
            )
            enqueue_outbox(
                OUTBOX_CREATE,
                {"group_id": str(group.id)},
                "incident-im-group:" f"{group.id}:create:reopen:" f"{group.incident.updated_at.isoformat(timespec='microseconds')}",
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
        return group


def enqueue_reconcile(incident, *, resume_create=False):
    updated_at = incident.updated_at.isoformat(timespec="microseconds")
    payload = {"incident_id": incident.pk}
    if resume_create:
        payload["resume_create"] = True
    return enqueue_outbox(OUTBOX_RECONCILE, payload, f"incident-im-group:{incident.pk}:reconcile:{updated_at}:{int(resume_create)}",)


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
        kind=OUTBOX_ADD_MEMBERS, payload={"group_id": str(group_id)}, status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
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
        kind=OUTBOX_SEND_SUMMARY, payload=payload, status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
    ).exists():
        return
    consumed_id = (
        AlertOutbox.objects.filter(kind=OUTBOX_SEND_SUMMARY, payload=payload, status=AlertOutbox.Status.DELIVERED,)
        .order_by("-pk")
        .values_list("pk", flat=True)
        .first()
    )
    idempotency_key = (
        f"incident-im-group:{group.id}:send-summary" if consumed_id is None else f"incident-im-group:{group.id}:send-summary:resume:{consumed_id}"
    )
    enqueue_outbox(
        OUTBOX_SEND_SUMMARY, payload, idempotency_key,
    )


def enqueue_recovered_create(group):
    payload = {"group_id": str(group.id)}
    if AlertOutbox.objects.filter(
        kind=OUTBOX_CREATE, payload=payload, status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
    ).exists():
        return
    previous_id = AlertOutbox.objects.filter(kind=OUTBOX_CREATE, payload=payload).order_by("-pk").values_list("pk", flat=True).first()
    idempotency_key = f"incident-im-group:{group.id}:create" if previous_id is None else f"incident-im-group:{group.id}:create:resume:{previous_id}"
    enqueue_outbox(OUTBOX_CREATE, payload, idempotency_key)
