from django.db import transaction
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.members import get_desired_usernames
from apps.alerts.service.outbox import enqueue_outbox
from apps.system_mgmt.services.im_group_service import IMGroupRuntimeService


OUTBOX_CREATE = "incident_im_group.create"
OUTBOX_ADD_MEMBERS = "incident_im_group.add_members"
OUTBOX_SEND_SUMMARY = "incident_im_group.send_summary"
OUTBOX_RECONCILE = "incident_im_group.reconcile"
MEMBER_BATCH_SIZE = 50


class IncidentIMRetryableError(RuntimeError):
    pass


def deliver_create_group(group_id) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        if group.external_chat_id:
            should_create = False
        else:
            should_create = True
            group.status = IncidentIMGroup.Status.CREATING
            group.current_stage = IncidentIMGroup.Stage.CREATING_CHAT
            group.save(update_fields=["status", "current_stage"])

    if not should_create:
        _enqueue_add_members(group_id)
        return

    members = list(
        IncidentIMMember.objects.filter(
            group_id=group_id,
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
            sync_status__in=[IncidentIMMember.SyncStatus.PENDING, IncidentIMMember.SyncStatus.FAILED],
        ).order_by("id")
    )
    member_ids = _initial_member_ids(group, members)
    result = IMGroupRuntimeService.execute(
        group.channel,
        operation="create_group",
        group_name=group.group_name,
        owner_id=group.external_owner_id,
        member_ids=member_ids,
        member_id_type=group.member_id_type,
        idempotency_key=group.idempotency_key,
    )
    if _raise_if_retryable(result):
        return
    if not result.success:
        _finish_create_failure(group_id, result)
        return

    chat_id = str((result.payload or {}).get("chat_id") or "").strip()
    if not chat_id:
        _finish_create_failure(
            group_id,
            _SyntheticFailure("provider.invalid_response", "飞书建群成功响应缺少 chat_id"),
        )
        return

    invalid_ids = set((result.payload or {}).get("invalid_member_ids") or [])
    now = timezone.now()
    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED:
            return
        locked.external_chat_id = chat_id
        locked.current_stage = IncidentIMGroup.Stage.ADDING_MEMBERS
        locked.last_error_code = ""
        locked.last_error_message = ""
        locked.save(
            update_fields=[
                "external_chat_id",
                "current_stage",
                "last_error_code",
                "last_error_message",
            ]
        )
        _save_member_result(
            locked,
            member_ids,
            invalid_ids,
            now=now,
            error_code="IM_MEMBER_INVALID",
            error_message="外部用户标识无效",
        )

    # chat_id 与首批成员事实已独立提交；此处崩溃时重放绝不会再次建群。
    _enqueue_add_members(group_id)


def deliver_add_members(group_id) -> None:
    group = _get_group(group_id)
    if group is None or _is_group_delivery_paused(group):
        return
    if not group.external_chat_id:
        _finish_create_failure(
            group_id,
            _SyntheticFailure("IM_CHAT_ID_MISSING", "协作群尚未取得外部 chat_id"),
        )
        return

    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or _is_group_delivery_paused(locked):
            return
        locked.current_stage = IncidentIMGroup.Stage.ADDING_MEMBERS
        locked.save(update_fields=["current_stage"])
        group = locked

    processed_member_ids: set[int] = set()
    while True:
        with transaction.atomic():
            locked = _lock_group(group_id)
            if locked is None or _is_group_delivery_paused(locked):
                return
            group = locked
            desired_usernames = get_desired_usernames(locked.incident)
        batch = list(
            IncidentIMMember.objects.filter(
                group_id=group_id,
                username__in=desired_usernames,
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            )
            .exclude(pk__in=processed_member_ids)
            .exclude(external_id="")
            .order_by("id")[:MEMBER_BATCH_SIZE]
        )
        if not batch:
            break
        processed_member_ids.update(member.pk for member in batch)
        member_ids = list(dict.fromkeys(member.external_id for member in batch))
        result = IMGroupRuntimeService.execute(
            group.channel,
            operation="add_members",
            chat_id=group.external_chat_id,
            member_ids=member_ids,
            member_id_type=group.member_id_type,
        )
        if _raise_if_retryable(result):
            return
        error_code, error_message = _result_error(result)
        if not result.success and error_code == "provider.group_not_found":
            _mark_degraded(group_id, error_code, error_message)
            return
        invalid_ids = set((result.payload or {}).get("invalid_member_ids") or [])
        if not result.success:
            invalid_ids = set(member_ids)
        elif invalid_ids:
            error_code = "IM_MEMBER_INVALID"
            error_message = "外部用户标识无效"
        with transaction.atomic():
            locked = _lock_group(group_id)
            if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED:
                return
            _save_member_result(
                locked,
                member_ids,
                invalid_ids,
                now=timezone.now(),
                error_code=error_code or "IM_MEMBER_ADD_FAILED",
                error_message=error_message or "邀请成员失败",
            )

    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or _is_group_delivery_paused(locked):
            return
        locked.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
        locked.save(update_fields=["current_stage"])
    enqueue_outbox(
        OUTBOX_SEND_SUMMARY,
        {"group_id": str(group_id)},
        f"incident-im-group:{group_id}:send-summary",
    )


def deliver_summary(group_id) -> None:
    group = _get_group(group_id)
    if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
        return
    if not group.external_chat_id:
        _finish_create_failure(
            group_id,
            _SyntheticFailure("IM_CHAT_ID_MISSING", "协作群尚未取得外部 chat_id"),
        )
        return

    result = IMGroupRuntimeService.execute(
        group.channel,
        operation="send_group_message",
        chat_id=group.external_chat_id,
        content=_build_incident_summary(group),
        idempotency_key=f"bklite-summary-{group.id.hex}",
    )
    if _raise_if_retryable(result):
        return
    error_code, error_message = _result_error(result)
    if not result.success and error_code == "provider.group_not_found":
        _mark_degraded(group_id, error_code, error_message)
        return

    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED:
            return
        has_member_gaps = locked.members.exclude(
            sync_status=IncidentIMMember.SyncStatus.JOINED
        ).exists()
        locked.current_stage = IncidentIMGroup.Stage.COMPLETED
        locked.status = (
            IncidentIMGroup.Status.ACTIVE
            if result.success and not has_member_gaps
            else IncidentIMGroup.Status.ACTIVE_PARTIAL
        )
        locked.last_error_code = "" if result.success else error_code
        locked.last_error_message = "" if result.success else error_message
        locked.last_sync_at = timezone.now()
        locked.save(
            update_fields=[
                "current_stage",
                "status",
                "last_error_code",
                "last_error_message",
                "last_sync_at",
            ]
        )


def handle_delivery_exhausted(kind: str, payload: dict, error: str) -> None:
    if kind not in {OUTBOX_CREATE, OUTBOX_ADD_MEMBERS, OUTBOX_SEND_SUMMARY}:
        return
    group_id = (payload or {}).get("group_id")
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.status = (
            IncidentIMGroup.Status.ACTIVE_PARTIAL
            if group.external_chat_id
            else IncidentIMGroup.Status.CREATE_FAILED
        )
        group.last_error_code = "IM_DELIVERY_EXHAUSTED"
        group.last_error_message = str(error or "投递重试已耗尽")[:500]
        group.save(
            update_fields=[
                "current_stage",
                "status",
                "last_error_code",
                "last_error_message",
            ]
        )


def _enqueue_add_members(group_id) -> None:
    enqueue_outbox(
        OUTBOX_ADD_MEMBERS,
        {"group_id": str(group_id)},
        f"incident-im-group:{group_id}:add-members",
    )


def _get_group(group_id):
    return IncidentIMGroup.objects.select_related("channel", "channel__integration_instance", "incident").filter(
        pk=group_id
    ).first()


def _lock_group(group_id):
    return IncidentIMGroup.objects.select_for_update().select_related(
        "channel", "channel__integration_instance", "incident"
    ).filter(pk=group_id).first()


def _is_group_delivery_paused(group):
    return (
        group.status in (IncidentIMGroup.Status.PAUSED, IncidentIMGroup.Status.UNLINKED)
        or bool(group.pause_reason)
        or group.incident.status not in IncidentStatus.ACTIVATE_STATUS
    )


def _initial_member_ids(group, members) -> list[str]:
    ids = [group.external_owner_id]
    ids.extend(member.external_id for member in members)
    return list(dict.fromkeys(external_id for external_id in ids if external_id))[:MEMBER_BATCH_SIZE]


def _save_member_result(group, member_ids, invalid_ids, *, now, error_code, error_message):
    members = list(
        group.members.select_for_update().filter(
            external_id__in=member_ids,
            mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        )
    )
    for member in members:
        member.updated_at = now
        member.attempt_count += 1
        if member.external_id in invalid_ids:
            member.sync_status = IncidentIMMember.SyncStatus.FAILED
            member.last_error_code = error_code
            member.last_error_message = error_message[:500]
        else:
            member.sync_status = IncidentIMMember.SyncStatus.JOINED
            member.last_error_code = ""
            member.last_error_message = ""
            member.joined_at = now
    if members:
        IncidentIMMember.objects.bulk_update(
            members,
            [
                "sync_status",
                "attempt_count",
                "last_error_code",
                "last_error_message",
                "joined_at",
                "updated_at",
            ],
        )


def _raise_if_retryable(result) -> bool:
    if result.success:
        return False
    if result.retryable or any(error.retryable for error in result.errors):
        raise IncidentIMRetryableError(result.summary)
    return False


def _result_error(result) -> tuple[str, str]:
    if result.errors:
        return result.errors[0].code, result.errors[0].message
    return "IM_PROVIDER_FAILED", result.summary


def _finish_create_failure(group_id, result) -> None:
    error_code, error_message = _result_error(result)
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        group.status = IncidentIMGroup.Status.CREATE_FAILED
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.last_error_code = error_code
        group.last_error_message = error_message[:500]
        group.save(
            update_fields=["status", "current_stage", "last_error_code", "last_error_message"]
        )


def _mark_degraded(group_id, error_code, error_message) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        group.status = IncidentIMGroup.Status.DEGRADED
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.last_error_code = error_code
        group.last_error_message = error_message[:500]
        group.save(
            update_fields=["status", "current_stage", "last_error_code", "last_error_message"]
        )


def _build_incident_summary(group) -> str:
    incident = group.incident
    return "\n".join(
        [
            f"Incident：{incident.title}",
            f"编号：{incident.incident_id}",
            f"级别：{incident.level}",
            "请在 BK-Lite Incident 详情中持续协作与更新进展。",
        ]
    )


class _SyntheticFailure:
    success = False
    retryable = False
    errors = ()

    def __init__(self, code, summary):
        self.summary = summary
        self.errors = (_SyntheticError(code, summary),)


class _SyntheticError:
    retryable = False

    def __init__(self, code, message):
        self.code = code
        self.message = message
