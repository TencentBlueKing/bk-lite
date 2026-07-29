import uuid

from django.db import models

from apps.base.models import User as AuthUser
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class IncidentIMGroup(MaintainerInfo, TimeInfo):
    class Status(models.TextChoices):
        PENDING_CREATE = "pending_create", "待创建"
        CREATING = "creating", "创建中"
        ACTIVE = "active", "正常"
        ACTIVE_PARTIAL = "active_partial", "部分成功"
        PAUSED = "paused", "已暂停"
        DEGRADED = "degraded", "配置异常"
        CREATE_FAILED = "create_failed", "创建失败"
        UNLINKED = "unlinked", "已解绑"

    class Stage(models.TextChoices):
        QUEUED = "queued", "已提交"
        CREATING_CHAT = "creating_chat", "创建群"
        ADDING_MEMBERS = "adding_members", "邀请成员"
        SENDING_SUMMARY = "sending_summary", "发送摘要"
        COMPLETED = "completed", "已完成"

    class PauseReason(models.TextChoices):
        MANUAL = "manual", "手工暂停"
        INCIDENT_CLOSED = "incident_closed", "Incident 已关闭"

    # 群主来自 IM 映射，但审计操作者来自认证用户，需覆盖 MaintainerInfo 的全局 32 字符默认值。
    created_by = models.CharField(
        "Creator",
        max_length=AuthUser._meta.get_field("username").max_length,
        default="",
    )
    updated_by = models.CharField(
        "Updater",
        max_length=AuthUser._meta.get_field("username").max_length,
        default="",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    incident = models.ForeignKey("alerts.Incident", on_delete=models.CASCADE, related_name="im_groups")
    channel = models.ForeignKey(
        "system_mgmt.IMNotificationChannel",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incident_im_groups",
    )
    provider_key = models.CharField(max_length=32, default="feishu")
    channel_name_snapshot = models.CharField(max_length=100)
    member_id_type = models.CharField(max_length=32)
    group_name = models.CharField(max_length=255)
    external_chat_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    external_owner_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING_CREATE, db_index=True)
    active_slot = models.PositiveSmallIntegerField(null=True, default=1, editable=False)
    current_stage = models.CharField(max_length=32, choices=Stage.choices, default=Stage.QUEUED)
    continuous_sync_enabled = models.BooleanField(default=True)
    resume_after_reopen = models.BooleanField(default=False)
    pause_reason = models.CharField(max_length=32, choices=PauseReason.choices, blank=True, default="")
    idempotency_key = models.CharField(max_length=50, unique=True)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_error_message = models.CharField(max_length=500, blank=True, default="")
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_reconcile_attempt_at = models.DateTimeField(null=True, blank=True)
    unlinked_at = models.DateTimeField(null=True, blank=True)
    unlinked_by = models.CharField(
        max_length=AuthUser._meta.get_field("username").max_length,
        blank=True,
        default="",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "active_slot"],
                name="unique_active_incident_im_group",
            )
        ]

    def save(self, *args, **kwargs):
        self.active_slot = None if self.status == self.Status.UNLINKED else 1
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"active_slot"}
        return super().save(*args, **kwargs)


class IncidentIMMember(TimeInfo):
    class Role(models.TextChoices):
        OPERATOR = "operator", "负责人"
        COLLABORATOR = "collaborator", "协作人"

    class MappingStatus(models.TextChoices):
        MAPPED = "mapped", "已映射"
        UNMAPPED = "unmapped", "未映射"
        CONFLICT = "conflict", "映射冲突"

    class SyncStatus(models.TextChoices):
        WAITING = "waiting", "等待映射"
        PENDING = "pending", "待同步"
        ADDING = "adding", "同步中"
        JOINED = "joined", "已入群"
        FAILED = "failed", "同步失败"

    group = models.ForeignKey(IncidentIMGroup, on_delete=models.CASCADE, related_name="members")
    username = models.CharField(max_length=150)
    role = models.CharField(max_length=32, choices=Role.choices)
    external_id = models.CharField(max_length=255, blank=True, default="")
    external_id_type = models.CharField(max_length=32, blank=True, default="")
    mapping_status = models.CharField(max_length=32, choices=MappingStatus.choices, default=MappingStatus.UNMAPPED)
    sync_status = models.CharField(max_length=32, choices=SyncStatus.choices, default=SyncStatus.WAITING)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=128, blank=True, default="")
    last_error_message = models.CharField(max_length=500, blank=True, default="")
    joined_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["group", "username"], name="unique_incident_im_member_username"),
        ]
        indexes = [
            models.Index(fields=["group", "sync_status"], name="incident_im_member_sync_idx"),
            models.Index(fields=["group", "mapping_status"], name="incident_im_member_mapping_idx"),
        ]
