from django.db import models
from django.db.models import Q

from apps.cmdb.collection.field_reconcile import MEMBER_SCOPE
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CollectReconcile(MaintainerInfo, TimeInfo):
    """一条数据调和。不是采集任务，没有周期和凭据。"""

    name = models.CharField(max_length=128)
    model_id = models.CharField(max_length=64, db_index=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = "cmdb_collect_reconcile"
        constraints = [
            models.UniqueConstraint(fields=["name", "model_id"], name="uniq_cmdb_reconcile_name_model"),
        ]

    def is_effective(self) -> bool:
        return self.orders.filter(scope=MEMBER_SCOPE).count() >= 2


class CollectReconcileOrder(models.Model):
    """成员顺序和字段顺序存在同一张表。position 越小越优先。"""

    reconcile = models.ForeignKey(CollectReconcile, on_delete=models.CASCADE, related_name="orders")
    scope = models.CharField(max_length=64)
    task = models.ForeignKey("cmdb.CollectModels", on_delete=models.CASCADE, related_name="reconcile_orders")
    position = models.PositiveIntegerField()

    class Meta:
        db_table = "cmdb_collect_reconcile_order"
        constraints = [
            models.UniqueConstraint(fields=["reconcile", "scope", "task"], name="uniq_cmdb_reconcile_order_task"),
            models.UniqueConstraint(fields=["reconcile", "scope", "position"], name="uniq_cmdb_reconcile_order_pos"),
            models.UniqueConstraint(fields=["task"], condition=Q(scope=MEMBER_SCOPE), name="uniq_cmdb_reconcile_member_task"),
        ]
        indexes = [
            models.Index(fields=["task", "scope"], name="idx_reconcile_order_task_scope"),
        ]
