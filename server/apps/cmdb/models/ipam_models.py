# -- coding: utf-8 --
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
