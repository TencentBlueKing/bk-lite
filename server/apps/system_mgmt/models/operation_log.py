from django.db import models
from django.db.models import JSONField

from apps.core.models.time_info import TimeInfo


class OperationLog(TimeInfo):
    """
    用户操作日志模型

    记录用户操作行为，包括：
    - 操作时间：使用 TimeInfo 的 created_at 字段
    - 用户：执行操作的用户名
    - 源IP：操作来源的 IP 地址
    - 应用：操作所属的应用模块
    - 动作类型：增删改查等操作类型
    - 概要描述：操作的详细描述信息
    """

    # 动作类型选项
    ACTION_CREATE = "create"
    ACTION_UPDATE = "update"
    ACTION_DELETE = "delete"
    ACTION_EXECUTE = "execute"

    ACTION_CHOICES = [
        (ACTION_CREATE, "Create"),
        (ACTION_UPDATE, "Update"),
        (ACTION_DELETE, "Delete"),
        (ACTION_EXECUTE, "Execute"),
    ]

    OUTCOME_SUCCESS = "success"
    OUTCOME_FAILURE = "failure"
    OUTCOME_ACCEPTED = "accepted"
    OUTCOME_UNRECORDED = ""

    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS, "Success"),
        (OUTCOME_FAILURE, "Failure"),
        (OUTCOME_ACCEPTED, "Accepted"),
        (OUTCOME_UNRECORDED, "Unrecorded"),
    ]

    username = models.CharField("Username", max_length=100, db_index=True)
    source_ip = models.GenericIPAddressField("Source IP", db_index=True)
    app = models.CharField("Application", max_length=100, db_index=True)
    action_type = models.CharField("Action Type", max_length=20, choices=ACTION_CHOICES, db_index=True)
    summary = models.TextField("Summary", blank=True, default="")
    domain = models.CharField("Domain", max_length=100, default="domain.com", db_index=True)
    target_type = models.CharField("Target Type", max_length=50, blank=True, default="", db_index=True)
    target_id = models.CharField("Target ID", max_length=100, blank=True, default="", db_index=True)
    target_name = models.CharField("Target Name", max_length=255, blank=True, default="", db_index=True)
    outcome = models.CharField(
        "Outcome",
        max_length=16,
        choices=OUTCOME_CHOICES,
        blank=True,
        default=OUTCOME_UNRECORDED,
        db_index=True,
    )
    failure_reason = models.TextField("Failure Reason", blank=True, default="")
    detail = JSONField("Detail", default=dict, blank=True)
    idempotency_key = models.CharField("Idempotency Key", max_length=128, null=True, blank=True, unique=True)

    class Meta:
        verbose_name = "Operation Log"
        verbose_name_plural = "Operation Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at", "action_type"]),
            models.Index(fields=["username", "-created_at"]),
            models.Index(fields=["app", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.action_type} - {self.app} - {self.created_at}"

    @staticmethod
    def display_fields():
        return [
            "id",
            "username",
            "source_ip",
            "app",
            "action_type",
            "summary",
            "domain",
            "created_at",
            "target_type",
            "target_id",
            "target_name",
            "outcome",
            "failure_reason",
            "detail",
        ]
