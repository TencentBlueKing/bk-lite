import ipaddress
import hashlib
import uuid
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.db import OperationalError, connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import AlertOutbox, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.constants import OUTBOX_ADD_MEMBERS, OUTBOX_CREATE, OUTBOX_SEND_SUMMARY
from apps.alerts.service.incident_im.groups import record_group_audit
from apps.alerts.service.incident_im.members import get_desired_operator_usernames, get_desired_usernames
from apps.alerts.service.incident_im.observability import emit_incident_im_event
from apps.alerts.service.outbox import enqueue_outbox
from apps.system_mgmt.services.im_group_service import IMGroupRuntimeService

MEMBER_BATCH_SIZE = 50
GROUP_DELIVERY_LEASE_SECONDS = 75


class IncidentIMRetryableError(RuntimeError):
    pass


class IncidentIMConfigurationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.safe_message = message


def deliver_create_group(group_id) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        if group.incident.status not in IncidentStatus.ACTIVATE_STATUS:
            _pause_create_for_closed_incident(group)
            return
        if group.status == IncidentIMGroup.Status.PAUSED or group.pause_reason:
            return
        if group.external_chat_id:
            should_create = False
        else:
            should_create = True
            desired_usernames = get_desired_usernames(group.incident)
            members = list(
                group.members.filter(
                    username__in=desired_usernames,
                    mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                    sync_status=IncidentIMMember.SyncStatus.PENDING,
                ).order_by("id")
            )
            current_operator_usernames = get_desired_operator_usernames(group.incident)
            owner_is_current = any(
                member.username in current_operator_usernames and member.external_id == group.external_owner_id for member in members
            )
            if not owner_is_current:
                group.status = IncidentIMGroup.Status.CREATE_FAILED
                group.current_stage = IncidentIMGroup.Stage.COMPLETED
                group.last_error_code = "IM_OWNER_NOT_CURRENT_OPERATOR"
                group.last_error_message = "建群负责人已不再是当前 Incident 负责人"
                group.save(
                    update_fields=["status", "current_stage", "last_error_code", "last_error_message",]
                )
                emit_incident_im_event(
                    "incident_im_group_delivery",
                    group_id=str(group.id),
                    incident_id=group.incident_id,
                    operation="create_group",
                    result="failed",
                    error_code=group.last_error_code,
                    member_count=len(members),
                )
                return
            group.status = IncidentIMGroup.Status.CREATING
            group.current_stage = IncidentIMGroup.Stage.CREATING_CHAT
            group.save(update_fields=["status", "current_stage"])

    if not should_create:
        _enqueue_add_members(group_id)
        return

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
    if _raise_if_retryable(
        result,
        group=group,
        operation="create_group",
        member_count=len(member_ids),
    ):
        return
    if not result.success:
        _finish_create_failure(group_id, result)
        return

    chat_id = str((result.payload or {}).get("chat_id") or "").strip()
    if not chat_id:
        _finish_create_failure(
            group_id, _SyntheticFailure("provider.invalid_response", "飞书建群成功响应缺少 chat_id"),
        )
        return

    invalid_ids = set((result.payload or {}).get("invalid_member_ids") or [])
    now = timezone.now()
    delivery_paused = False
    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED:
            return
        _pause_create_for_closed_incident(locked)
        locked.external_chat_id = chat_id
        locked.current_stage = IncidentIMGroup.Stage.ADDING_MEMBERS
        locked.last_error_code = ""
        locked.last_error_message = ""
        locked.save(
            update_fields=["external_chat_id", "current_stage", "last_error_code", "last_error_message",]
        )
        joined_count, failed_count = _save_member_result(
            locked, member_ids, invalid_ids, now=now, error_code="IM_MEMBER_INVALID", error_message="外部用户标识无效",
        )
        delivery_paused = _is_group_delivery_paused(locked)
        emit_incident_im_event(
            "incident_im_group_delivery",
            group_id=str(locked.id),
            incident_id=locked.incident_id,
            operation="create_group",
            result="partial" if failed_count else "success",
            member_count=len(member_ids),
            joined_count=joined_count,
            failed_count=failed_count,
            invalid_count=len(invalid_ids),
        )

    # chat_id 与首批成员事实已独立提交；此处崩溃时重放绝不会再次建群。
    if delivery_paused:
        return
    _enqueue_add_members(group_id)


def deliver_add_members(group_id, *, member_pks=None, delivery_claim=None) -> None:
    group = _get_group(group_id)
    if group is None or _is_group_delivery_paused(group):
        return
    if not group.external_chat_id:
        _finish_create_failure(
            group_id, _SyntheticFailure("IM_CHAT_ID_MISSING", "协作群尚未取得外部 chat_id"),
        )
        return

    lease_token = _acquire_group_delivery_lease(group_id)
    if lease_token is None:
        return
    if not lease_token:
        raise IncidentIMRetryableError("同一飞书群成员正在处理，请稍后重试")

    try:
        with transaction.atomic():
            locked = _lock_group(group_id)
            if locked is None or locked.delivery_lock_token != lease_token or _is_group_delivery_paused(locked):
                return
            locked.current_stage = IncidentIMGroup.Stage.ADDING_MEMBERS
            locked.save(update_fields=["current_stage"])
            group = locked
            desired_usernames = get_desired_usernames(locked.incident)
            batch_query = IncidentIMMember.objects.filter(
                group_id=group_id,
                username__in=desired_usernames,
                mapping_status=IncidentIMMember.MappingStatus.MAPPED,
                sync_status=IncidentIMMember.SyncStatus.PENDING,
            ).exclude(external_id="")
            if member_pks is not None:
                batch_query = batch_query.filter(pk__in=member_pks)
            batch = list(batch_query.order_by("id")[:MEMBER_BATCH_SIZE])
        if not batch:
            with transaction.atomic():
                locked = _lock_group(group_id)
                if locked is not None and locked.delivery_lock_token == lease_token and not _is_group_delivery_paused(locked):
                    _enqueue_next_add_batch_or_summary(locked)
                    _clear_group_delivery_lease(locked)
            return

        if not _delivery_claim_is_current(delivery_claim, group_id, lease_token):
            return

        member_ids = list(dict.fromkeys(member.external_id for member in batch))
        result = IMGroupRuntimeService.execute(
            group.channel, operation="add_members", chat_id=group.external_chat_id, member_ids=member_ids, member_id_type=group.member_id_type,
        )
        if _raise_if_retryable(
            result,
            group=group,
            operation="add_members",
            member_count=len(member_ids),
        ):
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
            if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED or locked.delivery_lock_token != lease_token:
                return
            joined_count, failed_count = _save_member_result(
                locked,
                member_ids,
                invalid_ids,
                now=timezone.now(),
                error_code=error_code or "IM_MEMBER_ADD_FAILED",
                error_message=error_message or "邀请成员失败",
            )
            record_group_audit(
                locked, locked.updated_by or locked.created_by or "system", f"补拉飞书群成员结果：成功 {joined_count} 人，失败 {failed_count} 人",
            )
            emit_incident_im_event(
                "incident_im_member_batch",
                group_id=str(locked.id),
                incident_id=locked.incident_id,
                operation="add_members",
                result="partial" if failed_count else "success",
                member_count=len(member_ids),
                joined_count=joined_count,
                failed_count=failed_count,
                invalid_count=len(invalid_ids),
                error_code=error_code if failed_count else "",
            )

        with transaction.atomic():
            locked = _lock_group(group_id)
            if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED or locked.delivery_lock_token != lease_token:
                return
            if not _is_group_delivery_paused(locked):
                _enqueue_next_add_batch_or_summary(locked)
            _clear_group_delivery_lease(locked)
    finally:
        IncidentIMGroup.objects.filter(pk=group_id, delivery_lock_token=lease_token).update(delivery_lock_token="", delivery_lock_expires_at=None)


def deliver_summary(group_id) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or _is_group_delivery_paused(group):
            return
        missing_chat_id = not group.external_chat_id
        is_initial_summary = group.last_sync_at is None

    if missing_chat_id:
        _finish_create_failure(
            group_id, _SyntheticFailure("IM_CHAT_ID_MISSING", "协作群尚未取得外部 chat_id"),
        )
        return

    try:
        content = _build_incident_summary(group)
    except IncidentIMConfigurationError as exc:
        result = _SyntheticFailure(exc.code, exc.safe_message)
    else:
        result = IMGroupRuntimeService.execute(
            group.channel,
            operation="send_group_message",
            chat_id=group.external_chat_id,
            content=content,
            idempotency_key=f"bklite-summary-{group.id.hex}",
        )
    if _raise_if_retryable(
        result,
        group=group,
        operation="send_summary",
        member_count=0,
    ):
        return
    error_code, error_message = _result_error(result)

    with transaction.atomic():
        locked = _lock_group(group_id)
        if locked is None or locked.status == IncidentIMGroup.Status.UNLINKED:
            return
        delivery_paused = _is_group_delivery_paused(locked)
        has_member_gaps = False
        if not delivery_paused:
            desired_usernames = get_desired_usernames(locked.incident)
            has_member_gaps = locked.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
        locked.current_stage = IncidentIMGroup.Stage.COMPLETED
        locked.last_error_code = "" if result.success else error_code
        locked.last_error_message = "" if result.success else error_message
        locked.last_sync_at = timezone.now()
        update_fields = [
            "current_stage",
            "last_error_code",
            "last_error_message",
            "last_sync_at",
        ]
        if not delivery_paused:
            if not result.success and error_code in {
                "provider.group_not_found",
                "IM_WEB_BASE_URL_MISSING",
                "IM_WEB_BASE_URL_INVALID",
            }:
                locked.status = IncidentIMGroup.Status.DEGRADED
            else:
                locked.status = IncidentIMGroup.Status.ACTIVE if result.success and not has_member_gaps else IncidentIMGroup.Status.ACTIVE_PARTIAL
            update_fields.append("status")
        locked.save(update_fields=update_fields)
        event = "创建飞书群最终结果" if is_initial_summary else "飞书群摘要发送结果"
        record_group_audit(
            locked, locked.updated_by or locked.created_by or "system", f"{event}：{'成功' if result.success else '失败'}",
        )
        emit_incident_im_event(
            "incident_im_group_delivery",
            group_id=str(locked.id),
            incident_id=locked.incident_id,
            operation="send_summary",
            result="success" if result.success else "failed",
            error_code="" if result.success else error_code,
            status=locked.status,
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
        group.last_error_code = "IM_DELIVERY_EXHAUSTED"
        group.last_error_message = str(error or "投递重试已耗尽")[:500]
        update_fields = ["current_stage", "last_error_code", "last_error_message"]
        if not _is_group_delivery_paused(group):
            group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL if group.external_chat_id else IncidentIMGroup.Status.CREATE_FAILED
            update_fields.append("status")
        group.save(update_fields=update_fields)
        failed_count = group.members.filter(sync_status__in=(IncidentIMMember.SyncStatus.PENDING, IncidentIMMember.SyncStatus.ADDING,)).count()
        if kind == OUTBOX_CREATE:
            overview = f"创建飞书群最终结果：失败，成功 0 人，失败 {failed_count} 人"
        elif kind == OUTBOX_ADD_MEMBERS:
            overview = f"补拉飞书群成员结果：成功 0 人，失败 {failed_count} 人"
        else:
            overview = "飞书群摘要发送结果：失败"
        record_group_audit(
            group, group.updated_by or group.created_by or "system", overview,
        )
        emit_incident_im_event(
            "incident_im_group_delivery",
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation=kind.removeprefix("incident_im_group."),
            result="failed",
            error_code="IM_DELIVERY_EXHAUSTED",
            failed_count=failed_count,
            status=group.status,
        )


def _enqueue_add_members(group_id) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or _is_group_delivery_paused(group):
            return
        if AlertOutbox.objects.filter(
            kind=OUTBOX_ADD_MEMBERS,
            payload__group_id=str(group.id),
            status__in=(AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING),
        ).exists():
            return
        _enqueue_next_add_batch_or_summary(group)


def enqueue_add_members_batch(group, *, allow_failed_retry=False) -> bool:
    desired_usernames = get_desired_usernames(group.incident)
    members = list(
        group.members.filter(
            username__in=desired_usernames, mapping_status=IncidentIMMember.MappingStatus.MAPPED, sync_status=IncidentIMMember.SyncStatus.PENDING,
        )
        .exclude(external_id="")
        .order_by("pk")[:MEMBER_BATCH_SIZE]
    )
    if not members:
        return False
    signature = "\0".join(
        f"{member.pk}:{member.external_id_type}:{member.external_id}:{member.attempt_count}"
        for member in members
    )
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()
    base_key = f"incident-im-group:{group.id}:add-members:{digest}"
    previous = (
        AlertOutbox.objects.filter(kind=OUTBOX_ADD_MEMBERS)
        .filter(Q(idempotency_key=base_key) | Q(idempotency_key__startswith=f"{base_key}:resume:"))
        .order_by("-pk")
        .first()
    )
    if previous is not None:
        if previous.status in (AlertOutbox.Status.PENDING, AlertOutbox.Status.DELIVERING):
            return True
        if previous.status == AlertOutbox.Status.FAILED and not allow_failed_retry:
            return False
        idempotency_key = f"{base_key}:resume:{previous.pk}"
    else:
        idempotency_key = base_key
    payload = {
        "group_id": str(group.id),
        "member_pks": [member.pk for member in members],
        "batch_digest": digest,
    }
    enqueue_outbox(
        OUTBOX_ADD_MEMBERS, payload, idempotency_key,
    )
    return True


def _enqueue_next_add_batch_or_summary(group) -> None:
    if enqueue_add_members_batch(group):
        return
    if group.last_sync_at is not None:
        desired_usernames = get_desired_usernames(group.incident)
        has_member_gaps = group.members.filter(username__in=desired_usernames).exclude(
            sync_status=IncidentIMMember.SyncStatus.JOINED
        ).exists()
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.status = IncidentIMGroup.Status.ACTIVE_PARTIAL if has_member_gaps else IncidentIMGroup.Status.ACTIVE
        group.last_sync_at = timezone.now()
        group.last_error_code = ""
        group.last_error_message = ""
        group.save(
            update_fields=[
                "current_stage",
                "status",
                "last_sync_at",
                "last_error_code",
                "last_error_message",
            ]
        )
        return
    group.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
    group.save(update_fields=["current_stage"])
    enqueue_outbox(
        OUTBOX_SEND_SUMMARY, {"group_id": str(group.id)}, f"incident-im-group:{group.id}:send-summary",
    )


def _acquire_group_delivery_lease(group_id):
    now = timezone.now()
    token = str(uuid.uuid4())
    eligible = (
        IncidentIMGroup.objects.filter(
            pk=group_id,
            pause_reason="",
            status__in=(
                IncidentIMGroup.Status.PENDING_CREATE,
                IncidentIMGroup.Status.CREATING,
                IncidentIMGroup.Status.ACTIVE,
                IncidentIMGroup.Status.ACTIVE_PARTIAL,
            ),
        )
        .filter(
            Q(delivery_lock_token="")
            | Q(delivery_lock_expires_at__isnull=True)
            | Q(delivery_lock_expires_at__lte=now)
        )
    )
    try:
        acquired = eligible.update(
            delivery_lock_token=token,
            delivery_lock_expires_at=now + timedelta(seconds=GROUP_DELIVERY_LEASE_SECONDS),
        )
    except OperationalError as exc:
        if _is_sqlite_lock_error(exc):
            return ""
        raise
    if acquired:
        group = _get_group(group_id)
        if group is not None and group.delivery_lock_token == token:
            return token
    group = _get_group(group_id)
    if group is None or _is_group_delivery_paused(group):
        return None
    return ""


def _clear_group_delivery_lease(group):
    group.delivery_lock_token = ""
    group.delivery_lock_expires_at = None
    group.save(update_fields=["delivery_lock_token", "delivery_lock_expires_at"])


def _delivery_claim_is_current(delivery_claim, group_id, lease_token):
    if delivery_claim and not AlertOutbox.objects.filter(
        pk=delivery_claim["record_id"],
        status=AlertOutbox.Status.DELIVERING,
        attempts=delivery_claim["generation"],
    ).exists():
        return False
    return IncidentIMGroup.objects.filter(
        pk=group_id,
        delivery_lock_token=lease_token,
        delivery_lock_expires_at__gt=timezone.now(),
        pause_reason="",
        status__in=(
            IncidentIMGroup.Status.PENDING_CREATE,
            IncidentIMGroup.Status.CREATING,
            IncidentIMGroup.Status.ACTIVE,
            IncidentIMGroup.Status.ACTIVE_PARTIAL,
        ),
        incident__status__in=IncidentStatus.ACTIVATE_STATUS,
    ).exists()


def _get_group(group_id):
    return IncidentIMGroup.objects.select_related("channel", "channel__integration_instance", "incident").filter(pk=group_id).first()


def _lock_group(group_id):
    return (
        IncidentIMGroup.objects.select_for_update().select_related("channel", "channel__integration_instance", "incident").filter(pk=group_id).first()
    )


def _is_group_delivery_paused(group):
    return (
        group.status in (IncidentIMGroup.Status.PAUSED, IncidentIMGroup.Status.UNLINKED)
        or bool(group.pause_reason)
        or group.incident.status not in IncidentStatus.ACTIVATE_STATUS
    )


def _is_sqlite_lock_error(exc):
    message = str(exc).lower()
    return connection.vendor == "sqlite" and (
        "database is locked" in message
        or "database table is locked" in message
        or "database is busy" in message
    )


def _pause_create_for_closed_incident(group) -> None:
    if (
        group.incident.status in IncidentStatus.ACTIVATE_STATUS
        or group.pause_reason == IncidentIMGroup.PauseReason.MANUAL
        or group.status not in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING, IncidentIMGroup.Status.PAUSED,)
    ):
        return
    group.status = IncidentIMGroup.Status.PAUSED
    group.pause_reason = IncidentIMGroup.PauseReason.INCIDENT_CLOSED
    group.resume_after_reopen = True
    group.save(update_fields=["status", "pause_reason", "resume_after_reopen"])


def _initial_member_ids(group, members) -> list[str]:
    ids = [group.external_owner_id]
    ids.extend(member.external_id for member in members)
    return list(dict.fromkeys(external_id for external_id in ids if external_id))[:MEMBER_BATCH_SIZE]


def _save_member_result(group, member_ids, invalid_ids, *, now, error_code, error_message):
    members = list(group.members.select_for_update().filter(external_id__in=member_ids, mapping_status=IncidentIMMember.MappingStatus.MAPPED,))
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
            members, ["sync_status", "attempt_count", "last_error_code", "last_error_message", "joined_at", "updated_at",],
        )
    failed_count = sum(member.sync_status == IncidentIMMember.SyncStatus.FAILED for member in members)
    return len(members) - failed_count, failed_count


def _raise_if_retryable(result, *, group, operation, member_count) -> bool:
    if result.success:
        return False
    if result.retryable or any(error.retryable for error in result.errors):
        error_code, _ = _result_error(result)
        emit_incident_im_event(
            (
                "incident_im_member_batch"
                if operation == "add_members"
                else "incident_im_group_delivery"
            ),
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation=operation,
            result="retrying",
            error_code=error_code,
            retryable=True,
            member_count=member_count,
        )
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
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.last_error_code = error_code
        group.last_error_message = error_message[:500]
        update_fields = ["current_stage", "last_error_code", "last_error_message"]
        if not _is_group_delivery_paused(group):
            group.status = IncidentIMGroup.Status.CREATE_FAILED
            update_fields.append("status")
        group.save(update_fields=update_fields)
        failed_count = group.members.filter(mapping_status=IncidentIMMember.MappingStatus.MAPPED,).count()
        record_group_audit(
            group, group.created_by or "system", f"创建飞书群最终结果：失败，成功 0 人，失败 {failed_count} 人",
        )
        emit_incident_im_event(
            "incident_im_group_delivery",
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation="create_group",
            result="failed",
            error_code=error_code,
            failed_count=failed_count,
            status=group.status,
        )


def _mark_degraded(group_id, error_code, error_message) -> None:
    with transaction.atomic():
        group = _lock_group(group_id)
        if group is None or group.status == IncidentIMGroup.Status.UNLINKED:
            return
        group.current_stage = IncidentIMGroup.Stage.COMPLETED
        group.last_error_code = error_code
        group.last_error_message = error_message[:500]
        update_fields = ["current_stage", "last_error_code", "last_error_message"]
        if not _is_group_delivery_paused(group):
            group.status = IncidentIMGroup.Status.DEGRADED
            update_fields.append("status")
        group.save(update_fields=update_fields)
        emit_incident_im_event(
            "incident_im_group_delivery",
            group_id=str(group.id),
            incident_id=group.incident_id,
            operation="add_members",
            result="failed",
            error_code=error_code,
            status=group.status,
        )


def _build_incident_summary(group) -> str:
    incident = group.incident
    operators = incident.operator or []
    if not isinstance(operators, (list, tuple)):
        operators = [operators]
    operator_names = "、".join(str(operator) for operator in operators if operator)
    query = urlencode({"id": incident.pk, "incident_id": incident.incident_id})
    path = f"/alarm/incidents/detail?{query}"
    base_url = _public_web_base_url()
    detail_url = f"{base_url}{path}"
    return "\n".join(
        [
            "Incident 协作群已建立",
            "",
            f"编号：{incident.incident_id}",
            f"标题：{incident.title}",
            f"级别：{incident.level}",
            f"状态：{incident.status}",
            f"负责人：{operator_names or '无'}",
            f"详情：{detail_url}",
        ]
    )


def _public_web_base_url() -> str:
    base_url = (getattr(settings, "WEB_BASE_URL", "") or "").strip().rstrip("/")
    if not base_url:
        raise IncidentIMConfigurationError(
            "IM_WEB_BASE_URL_MISSING", "WEB_BASE_URL 未配置或不可从飞书访问",
        )
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise IncidentIMConfigurationError("IM_WEB_BASE_URL_INVALID", "WEB_BASE_URL 必须配置为可从飞书访问的 HTTP(S) 绝对地址",) from exc
    is_valid = parsed.scheme in {"http", "https"} and bool(hostname) and not parsed.username and not parsed.password
    if is_valid:
        normalized_hostname = hostname.rstrip(".").lower()
        is_valid = normalized_hostname != "localhost" and not normalized_hostname.endswith(".localhost")
        try:
            ip_address = ipaddress.ip_address(normalized_hostname)
        except ValueError:
            pass
        else:
            is_valid = is_valid and ip_address.is_global
    if not is_valid:
        raise IncidentIMConfigurationError(
            "IM_WEB_BASE_URL_INVALID", "WEB_BASE_URL 必须配置为可从飞书访问的 HTTP(S) 绝对地址",
        )
    return base_url


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
