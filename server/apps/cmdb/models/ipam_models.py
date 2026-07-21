# -- coding: utf-8 --
import uuid

from django.db import models

from apps.core.models.time_info import TimeInfo


class IPAMReconcileSource(TimeInfo):
    """对账数据来源登记表：参与对账的 (模型, IP 字段)。规格 §5.1。"""

    model_id = models.CharField(max_length=128, help_text="参与对账的 CI 模型 id，如 host/network")
    ip_attr_id = models.CharField(max_length=128, help_text="该模型上承载 IP 的属性 id，如 ip_addr")
    enabled = models.BooleanField(default=True, help_text="是否启用")
    remark = models.CharField(max_length=256, blank=True, default="", help_text="备注")

    class Meta:
        db_table = "cmdb_ipam_reconcile_source"
        unique_together = ("model_id", "ip_attr_id")
        verbose_name = "IPAM对账来源"


class IPAMReconcileRunStatus(models.TextChoices):
    PENDING = "pending", "等待执行"
    RUNNING = "running", "执行中"
    SUCCESS = "success", "成功"
    ERROR = "error", "失败"


class IPAMReconcileRun(TimeInfo):
    """IPAM 全量对账的持久化执行记录与数据库所有权凭证。"""

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    active_scope = models.CharField(max_length=32, default="global", null=True, unique=True, editable=False)
    trigger = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16,
        choices=IPAMReconcileRunStatus.choices,
        default=IPAMReconcileRunStatus.PENDING,
    )
    owner_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "cmdb_ipam_reconcile_run"
        indexes = [models.Index(fields=["status", "lease_expires_at"], name="cmdb_ipam_run_lease_idx")]


# 默认对账来源：哪些 CI 模型的哪个属性承载 IP。由数据迁移预置（不再用单独的 management 命令）。
DEFAULT_RECONCILE_SOURCES = [
    ("host", "ip_addr"),
    ("network", "ip"),
]


def seed_reconcile_sources(model_cls):
    """幂等预置默认对账来源。data migration 用 apps.get_model 取到的模型类调用，单测直接传真实模型类。"""
    for model_id, ip_attr_id in DEFAULT_RECONCILE_SOURCES:
        model_cls.objects.get_or_create(
            model_id=model_id, ip_attr_id=ip_attr_id, defaults={"enabled": True}
        )
