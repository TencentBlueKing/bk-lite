import json
import uuid
from time import sleep

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import Count
from django.utils import timezone

from apps.alerts.constants.constants import IncidentStatus, LogAction, LogTargetType
from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.errors import IncidentIMError
from apps.alerts.service.incident_im.members import get_desired_usernames, resolve_incident_members
from apps.alerts.service.incident_im.observability import emit_incident_im_event
from apps.alerts.service.outbox import enqueue_outbox
from apps.alerts.utils.operator_log import record_operator_log_deferred_mirror
from apps.core.logger import alert_logger as logger
from apps.system_mgmt.services.im_group_service import IMGroupChannelError, IMGroupRuntimeService


def _emit_manual_lifecycle_after_commit(
    *, group_id, incident_id, operation, status, pause_reason=None,
):
    safe_group_id = str(group_id)
    safe_incident_id = incident_id
    safe_operation = str(operation)
    safe_status = str(status)
    safe_pause_reason = None if pause_reason is None else str(pause_reason)

    def emit(
        group_id=safe_group_id,
        incident_id=safe_incident_id,
        operation=safe_operation,
        status=safe_status,
        pause_reason=safe_pause_reason,
    ):
        fields = {
            "group_id": group_id,
            "incident_id": incident_id,
            "operation": operation,
            "result": "success",
            "status": status,
        }
        if pause_reason is not None:
            fields["pause_reason"] = pause_reason
        emit_incident_im_event("incident_im_lifecycle", **fields)

    transaction.on_commit(emit)


class IncidentIMGroupService:
    SQLITE_LOCK_RETRY_DELAYS = (0.01, 0.02, 0.04, 0.08, 0.16)

    @classmethod
    def create(
        cls, *, incident_id, actor, channel_id, group_name, owner_username, continuous_sync_enabled,
    ):
        for retry_index in range(len(cls.SQLITE_LOCK_RETRY_DELAYS) + 1):
            try:
                return cls._create_once(
                    incident_id=incident_id,
                    actor=actor,
                    channel_id=channel_id,
                    group_name=group_name,
                    owner_username=owner_username,
                    continuous_sync_enabled=continuous_sync_enabled,
                )
            except IntegrityError as exc:
                if cls._has_active_group(incident_id):
                    raise IncidentIMError("IM_GROUP_ACTIVE_EXISTS", "Incident 已存在未解绑的协作群", 409) from exc
                raise
            except OperationalError as exc:
                if not cls._is_sqlite_lock_error(exc):
                    raise
                if cls._has_active_group_after_sqlite_lock(incident_id):
                    raise IncidentIMError("IM_GROUP_ACTIVE_EXISTS", "Incident 已存在未解绑的协作群", 409) from exc
                if retry_index == len(cls.SQLITE_LOCK_RETRY_DELAYS):
                    raise
                sleep(cls.SQLITE_LOCK_RETRY_DELAYS[retry_index])

    @classmethod
    def _create_once(
        cls, *, incident_id, actor, channel_id, group_name, owner_username, continuous_sync_enabled,
    ):
        with transaction.atomic():
            incident = Incident.objects.select_for_update().filter(pk=incident_id).first()
            if incident is None:
                raise IncidentIMError("IM_INCIDENT_NOT_FOUND", "Incident 不存在", 404)
            cls.require_operator(incident, actor)
            if incident.status not in IncidentStatus.ACTIVATE_STATUS:
                raise IncidentIMError("IM_INCIDENT_NOT_ACTIVE", "Incident 已关闭或已处理，无法创建协作群", 409)
            if IncidentIMGroup.objects.filter(incident=incident, active_slot=1).exists():
                raise IncidentIMError("IM_GROUP_ACTIVE_EXISTS", "Incident 已存在未解绑的协作群", 409)

            channel = cls.require_ready_channel(actor, channel_id)
            member_id_type = str(channel.external_receive_field or "").strip()
            members = resolve_incident_members(incident, channel, member_id_type=member_id_type)
            mapped_operators = {
                member.username: member
                for member in members
                if member.role == IncidentIMMember.Role.OPERATOR and member.mapping_status == IncidentIMMember.MappingStatus.MAPPED
            }
            if not mapped_operators:
                raise IncidentIMError("IM_NO_MAPPED_OPERATOR", "至少需要一名已映射的负责人")
            owner = mapped_operators.get(owner_username)
            if owner is None:
                raise IncidentIMError("IM_OWNER_NOT_MAPPED", "所选群主必须是已映射的负责人")

            with transaction.atomic():
                group_id = uuid.uuid4()
                group = IncidentIMGroup.objects.create(
                    id=group_id,
                    incident=incident,
                    channel=channel,
                    provider_key=channel.integration_instance.provider_key,
                    channel_name_snapshot=channel.name,
                    member_id_type=member_id_type,
                    group_name=group_name,
                    external_owner_id=owner.external_id,
                    continuous_sync_enabled=continuous_sync_enabled,
                    idempotency_key=f"bklite-{group_id.hex}",
                    created_by=actor.username,
                    updated_by=actor.username,
                )
                IncidentIMMember.objects.bulk_create(
                    [
                        IncidentIMMember(
                            group=group,
                            username=member.username,
                            role=member.role,
                            external_id=member.external_id,
                            external_id_type=member.external_id_type,
                            mapping_status=member.mapping_status,
                            sync_status=(
                                IncidentIMMember.SyncStatus.PENDING
                                if member.mapping_status == IncidentIMMember.MappingStatus.MAPPED
                                else IncidentIMMember.SyncStatus.WAITING
                            ),
                            last_error_code=member.error_code,
                            last_error_message=member.error_message,
                        )
                        for member in members
                    ]
                )
                enqueue_outbox(
                    "incident_im_group.create", {"group_id": str(group.id)}, f"incident-im-group:{group.id}:create",
                )
                record_group_audit(
                    group, actor.username, f"创建飞书群请求，成员 {len(members)} 人", action=LogAction.ADD,
                )
        return group

    @classmethod
    def set_continuous_sync(cls, *, incident_id, actor_username, enabled):
        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            group.continuous_sync_enabled = enabled
            group.updated_by = actor_username
            group.save(update_fields=["continuous_sync_enabled", "updated_by", "updated_at"])
            record_group_audit(
                group, actor_username, f"持续同步设置为{'开启' if enabled else '关闭'}",
            )
            return group

    @classmethod
    def pause(cls, *, incident_id, actor_username):
        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            if group.status not in (IncidentIMGroup.Status.ACTIVE, IncidentIMGroup.Status.ACTIVE_PARTIAL,):
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不允许暂停", 409)
            group.status = IncidentIMGroup.Status.PAUSED
            group.pause_reason = IncidentIMGroup.PauseReason.MANUAL
            group.resume_after_reopen = False
            group.updated_by = actor_username
            group.save(
                update_fields=["status", "pause_reason", "resume_after_reopen", "updated_by", "updated_at",]
            )
            record_group_audit(group, actor_username, "暂停飞书群同步")
            _emit_manual_lifecycle_after_commit(
                group_id=str(group.id),
                incident_id=group.incident_id,
                operation="pause",
                status=group.status,
                pause_reason=group.pause_reason,
            )
            return group

    @classmethod
    def resume(cls, *, incident_id, actor_username):
        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            if incident.status not in IncidentStatus.ACTIVATE_STATUS:
                raise IncidentIMError("IM_INCIDENT_NOT_ACTIVE", "Incident 已关闭，无法手工恢复协作群", 409)
            if group.status != IncidentIMGroup.Status.PAUSED or group.pause_reason != IncidentIMGroup.PauseReason.MANUAL:
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不允许恢复", 409)
            desired_usernames = get_desired_usernames(group.incident)
            has_gap = group.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
            group.status = (
                IncidentIMGroup.Status.ACTIVE_PARTIAL
                if has_gap or group.current_stage != IncidentIMGroup.Stage.COMPLETED
                else IncidentIMGroup.Status.ACTIVE
            )
            group.pause_reason = ""
            group.resume_after_reopen = False
            group.updated_by = actor_username
            group.save(
                update_fields=["status", "pause_reason", "resume_after_reopen", "updated_by", "updated_at",]
            )
            record_group_audit(group, actor_username, "恢复飞书群同步")
            _emit_manual_lifecycle_after_commit(
                group_id=str(group.id),
                incident_id=group.incident_id,
                operation="resume",
                status=group.status,
            )
            return group

    @classmethod
    def retry_degraded(cls, *, incident_id, actor_username):
        from apps.alerts.service.incident_im.reconcile import _enqueue_recovered_summary

        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            if incident.status not in IncidentStatus.ACTIVATE_STATUS:
                raise IncidentIMError("IM_INCIDENT_NOT_ACTIVE", "Incident 已关闭，无法重试协作群", 409)
            if group.status != IncidentIMGroup.Status.DEGRADED:
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不需要外部漂移复核", 409)
            original_group_id = group.id
            original_active_slot = group.active_slot
            original_status = group.status
            original_error_code = group.last_error_code
            channel = group.channel
            external_chat_id = group.external_chat_id

        if channel is None or not external_chat_id:
            result = None
        else:
            result = IMGroupRuntimeService.execute(channel, operation="get_group", chat_id=external_chat_id,)

        with transaction.atomic():
            incident = Incident.objects.select_for_update().filter(pk=incident_id).first()
            if incident is None:
                raise IncidentIMError("IM_INCIDENT_NOT_FOUND", "Incident 不存在", 404)
            cls.require_operator_username(incident, actor_username)
            if incident.status not in IncidentStatus.ACTIVATE_STATUS:
                raise IncidentIMError("IM_INCIDENT_NOT_ACTIVE", "Incident 已关闭，无法重试协作群", 409)
            locked = (
                IncidentIMGroup.objects.select_for_update()
                .select_related("incident", "channel", "channel__integration_instance")
                .filter(pk=original_group_id, incident=incident)
                .first()
            )
            if locked is None or locked.active_slot != original_active_slot or locked.status != original_status:
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "协作群绑定已变化，请刷新后重试", 409)
            retry_summary = False
            if result is None or not result.success:
                code, message = cls._runtime_error(result)
                locked.status = IncidentIMGroup.Status.DEGRADED
                locked.last_error_code = code
                locked.last_error_message = message[:500]
            else:
                desired_usernames = get_desired_usernames(locked.incident)
                has_gap = locked.members.filter(username__in=desired_usernames).exclude(sync_status=IncidentIMMember.SyncStatus.JOINED).exists()
                retry_summary = original_error_code in {
                    "IM_WEB_BASE_URL_MISSING",
                    "IM_WEB_BASE_URL_INVALID",
                }
                locked.status = IncidentIMGroup.Status.ACTIVE_PARTIAL if has_gap or retry_summary else IncidentIMGroup.Status.ACTIVE
                if retry_summary:
                    locked.current_stage = IncidentIMGroup.Stage.SENDING_SUMMARY
                locked.last_error_code = ""
                locked.last_error_message = ""
            locked.updated_by = actor_username
            locked.save(
                update_fields=["status", "current_stage", "last_error_code", "last_error_message", "updated_by", "updated_at",]
            )
            if result is not None and result.success and retry_summary:
                _enqueue_recovered_summary(locked)
            record_group_audit(locked, actor_username, "重试飞书群并检查外部群状态")
            return locked

    @classmethod
    def prepare_create_retry(cls, *, incident_id, actor_username):
        from apps.alerts.service.incident_im.reconcile import enqueue_recovered_create

        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            if group.status != IncidentIMGroup.Status.CREATE_FAILED or group.external_chat_id:
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不允许重试创建", 409)
            group.status = IncidentIMGroup.Status.PENDING_CREATE
            group.current_stage = IncidentIMGroup.Stage.QUEUED
            group.last_error_code = ""
            group.last_error_message = ""
            group.updated_by = actor_username
            group.save(
                update_fields=["status", "current_stage", "last_error_code", "last_error_message", "updated_by", "updated_at",]
            )
            record_group_audit(group, actor_username, "重试创建飞书群")
            enqueue_recovered_create(group)
            return group

    @classmethod
    def unlink(cls, *, incident_id, actor_username, group_name):
        with transaction.atomic():
            incident, group = cls._lock_incident_and_active_group(incident_id)
            if group is None:
                raise IncidentIMError("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", 404)
            cls.require_operator_username(incident, actor_username)
            if group.group_name != group_name:
                raise IncidentIMError("IM_GROUP_NAME_MISMATCH", "群名称确认不匹配")
            if (
                group.status in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING,)
                or group.current_stage != IncidentIMGroup.Stage.COMPLETED
                or group.members.filter(sync_status=IncidentIMMember.SyncStatus.ADDING).exists()
            ):
                raise IncidentIMError("IM_GROUP_BUSY", "协作群仍有任务执行中，暂不能解绑", 409)
            group.status = IncidentIMGroup.Status.UNLINKED
            group.active_slot = None
            group.unlinked_at = timezone.now()
            group.unlinked_by = actor_username
            group.updated_by = actor_username
            group.save(
                update_fields=["status", "active_slot", "unlinked_at", "unlinked_by", "updated_by", "updated_at",]
            )
            record_group_audit(
                group, actor_username, "解绑飞书群，本地停止管理，外部群保留", action=LogAction.DELETE,
            )
            return group

    @staticmethod
    def _has_active_group(incident_id):
        return IncidentIMGroup.objects.filter(incident_id=incident_id, active_slot=1).exists()

    @classmethod
    def _has_active_group_after_sqlite_lock(cls, incident_id):
        try:
            return cls._has_active_group(incident_id)
        except OperationalError as exc:
            if cls._is_sqlite_lock_error(exc):
                return False
            raise

    @staticmethod
    def _is_sqlite_lock_error(exc):
        message = str(exc).lower()
        return connection.vendor == "sqlite" and (
            "database is locked" in message or "database table is locked" in message or "database is busy" in message
        )

    @staticmethod
    def _lock_incident_and_active_group(incident_id):
        incident = Incident.objects.select_for_update().filter(pk=incident_id).first()
        if incident is None:
            raise IncidentIMError("IM_INCIDENT_NOT_FOUND", "Incident 不存在", 404)
        group = (
            IncidentIMGroup.objects.select_for_update()
            .select_related("incident", "channel", "channel__integration_instance")
            .filter(incident=incident, active_slot=1)
            .first()
        )
        return incident, group

    @staticmethod
    def _runtime_error(result):
        if result is None:
            return "IM_CHANNEL_NOT_READY", "协作群渠道不可用"
        if result.errors:
            return result.errors[0].code, result.errors[0].message
        return "IM_PROVIDER_FAILED", result.summary

    @staticmethod
    def require_operator(incident, actor):
        if getattr(actor, "username", "") not in (incident.operator or []):
            raise IncidentIMError("IM_OPERATOR_REQUIRED", "只有 Incident 负责人可以管理协作群", 403)

    @staticmethod
    def require_operator_username(incident, actor_username):
        if actor_username not in (incident.operator or []):
            raise IncidentIMError("IM_OPERATOR_REQUIRED", "只有 Incident 负责人可以管理协作群", 403)

    @staticmethod
    def require_ready_channel(actor, channel_id):
        try:
            return IMGroupRuntimeService.require_ready_channel(actor, channel_id)
        except IMGroupChannelError as exc:
            if exc.code == "im_group.channel_access_denied":
                raise IncidentIMError("IM_CHANNEL_FORBIDDEN", "无权使用该协作群渠道", 403) from exc
            raise IncidentIMError("IM_CHANNEL_NOT_READY", "协作群渠道未就绪或不可用") from exc


def record_group_audit(group, actor_username, overview, *, action=LogAction.MODIFY):
    counts = {item["sync_status"]: item["count"] for item in group.members.values("sync_status").annotate(count=Count("id"))}
    payload = {
        "channel_name_snapshot": group.channel_name_snapshot,
        "binding_id": str(group.id),
        "member_result": {
            "total": sum(counts.values()),
            "joined": counts.get(IncidentIMMember.SyncStatus.JOINED, 0),
            "waiting": counts.get(IncidentIMMember.SyncStatus.WAITING, 0),
            "pending": counts.get(IncidentIMMember.SyncStatus.PENDING, 0),
            "adding": counts.get(IncidentIMMember.SyncStatus.ADDING, 0),
            "failed": counts.get(IncidentIMMember.SyncStatus.FAILED, 0),
        },
    }
    structured_overview = f"{overview} | {json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    try:
        with transaction.atomic():
            return record_operator_log_deferred_mirror(
                action=action,
                target_type=LogTargetType.INCIDENT,
                operator=actor_username or "system",
                operator_object=f"飞书协作群[{group.id}]",
                target_id=group.incident.incident_id,
                overview=structured_overview,
            )
    except Exception as exc:  # noqa: BLE001 — 审计失败不得回滚已完成的群管理动作
        logger.warning(
            "record Incident IM group audit failed, group_id=%s, action=%s, error_type=%s", group.id, action, type(exc).__name__,
        )
        return None
