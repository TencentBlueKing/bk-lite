from django.db import models
from django.db.models import Q


class AutoRelationPending(models.Model):
    """待重算的自动关联。实例变更和规则变更各占一行，重复写入保持原行。"""

    instance_id = models.BigIntegerField(null=True, unique=True)
    model_asst_id = models.CharField(max_length=255, null=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cmdb_auto_relation_pending"
        constraints = [
            models.CheckConstraint(
                check=(Q(instance_id__isnull=False, model_asst_id__isnull=True) | Q(instance_id__isnull=True, model_asst_id__isnull=False)),
                name="cmdb_auto_relation_pending_one_target",
            ),
        ]
