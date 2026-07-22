import hashlib

from django.db import transaction

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.members import reconcile_member_snapshots
from apps.alerts.service.outbox import enqueue_outbox


OUTBOX_ADD_MEMBERS = "incident_im_group.add_members"
OUTBOX_RECONCILE = "incident_im_group.reconcile"
SYNCABLE_GROUP_STATUSES = (
    IncidentIMGroup.Status.ACTIVE,
    IncidentIMGroup.Status.ACTIVE_PARTIAL,
)


def reconcile_incident_im_group(incident_id, force_delivery=False):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None:
            return None

        reconcile_member_snapshots(group, group.incident)
        if (
            group.status == IncidentIMGroup.Status.ACTIVE
            and group.members.exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        ):
            group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL
            group.save(update_fields=["status"])
        if not _can_deliver(group, force_delivery=force_delivery):
            return group

        pending = list(
            group.members.filter(
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status__in=(
                    IncidentIMMember.SyncStatus.PENDING,
                    IncidentIMMember.SyncStatus.FAILED,
                ),
            )
            .exclude(external_id="")
            .order_by("pk")
        )
        if pending and not _has_unfinished_add_members(group.id):
            signature = "\0".join(
                f"{member.pk}:{member.updated_at.isoformat(timespec='microseconds')}"
                for member in pending
            )
            digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
            enqueue_outbox(
                OUTBOX_ADD_MEMBERS,
                {"group_id": str(group.id)},
                f"incident-im-group:{group.id}:add-members:{digest}",
            )
        return group


def reconcile_incident_im_group_by_group_id(group_id, force_delivery=False):
    incident_id = (
        IncidentIMGroup.objects.filter(pk=group_id, active_slot=1)
        .values_list("incident_id", flat=True)
        .first()
    )
    if incident_id is None:
        return None
    return reconcile_incident_im_group(incident_id, force_delivery=force_delivery)


def pause_group_for_closed_incident(incident_id):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None or group.pause_reason == IncidentIMGroup.PauseReason.MANUAL:
            return group
        group.resume_after_reopen = group.continuous_sync_enabled
        group.status = IncidentIMGroup.Status.PAUSED
        group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
        group.save(update_fields=["resume_after_reopen", "status", "pause_reason"])
        return group


def resume_group_for_reopened_incident(incident_id):
    with transaction.atomic():
        group = _lock_active_group_for_incident(incident_id)
        if group is None or group.pause_reason != IncidentIMGroup.PauseReason.INCIDENT_CLOSED:
            return group

        should_resume = group.resume_after_reopen
        has_member_gap = group.members.exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        group.status = (
            IncidentIMGroup.Status.ACTIVE_PARTIAL
            if has_member_gap
            else IncidentIMGroup.Status.ACTIVE
        )
        group.pause_reason = ""
        group.resume_after_reopen = False
        group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])
        if should_resume:
            enqueue_reconcile(group.incident)
        return group


def enqueue_reconcile(incident):
    updated_at = incident.updated_at.isoformat(timespec="microseconds")
    return enqueue_outbox(
        OUTBOX_RECONCILE,
        {"incident_id": incident.pk},
        f"incident-im-group:{incident.pk}:reconcile:{updated_at}",
    )


def _lock_active_group_for_incident(incident_id):
    return (
        IncidentIMGroup.objects.select_for_update()
        .select_related("incident", "channel", "channel__integration_instance")
        .filter(incident_id=incident_id, active_slot=1)
        .first()
    )


def _can_deliver(group, force_delivery):
    return (
        group.status in SYNCABLE_GROUP_STATUSES
        and not group.pause_reason
        and group.incident.status in IncidentStatus.ACTIVATE_STATUS
        and (group.continuous_sync_enabled or force_delivery)
    )


def _has_unfinished_add_members(group_id):
    return AlertOutbox.objects.filter(
        kind=OUTBOX_ADD_MEMBERS,
        payload={"group_id": str(group_id)},
        status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
    ).exists()
