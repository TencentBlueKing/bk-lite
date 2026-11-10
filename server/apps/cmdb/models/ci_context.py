from django.db import models
from django.db.models import Q

from apps.cmdb.services.ci_context_policy import CONTEXT_APPLICATION


class CmdbCiContext(models.Model):
    """CI 到应用的旁路成员索引。"""

    ci_uuid = models.CharField(max_length=64)
    context = models.CharField(max_length=32, default=CONTEXT_APPLICATION)
    root_uuid = models.CharField(max_length=64)
    root_model = models.CharField(max_length=64, default="application")
    ci_model = models.CharField(max_length=64)
    ip_addr = models.CharField(max_length=255, blank=True, default="")
    organization = models.JSONField(default=list)
    system_uuid = models.CharField(max_length=64, null=True, blank=True)
    layer = models.PositiveSmallIntegerField()
    via_uuid = models.CharField(max_length=64, null=True, blank=True)
    model_asst_id = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cmdb_ci_context"
        unique_together = [("ci_uuid", "context", "root_uuid")]
        indexes = [
            models.Index(fields=["ci_uuid", "context"]),
            models.Index(fields=["ci_model", "ip_addr"]),
        ]


class CmdbCiContextPending(models.Model):
    """待重算的 CI 上下文。应用、关联规则、实例各占一行，重复写入保持原行。"""

    root_uuid = models.CharField(max_length=64, null=True, unique=True)
    model_asst_id = models.CharField(max_length=255, null=True, unique=True)
    ci_uuid = models.CharField(max_length=64, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cmdb_ci_context_pending"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(root_uuid__isnull=False, model_asst_id__isnull=True, ci_uuid__isnull=True)
                    | Q(root_uuid__isnull=True, model_asst_id__isnull=False, ci_uuid__isnull=True)
                    | Q(root_uuid__isnull=True, model_asst_id__isnull=True, ci_uuid__isnull=False)
                ),
                name="cmdb_ci_context_pending_one_target",
            ),
        ]
