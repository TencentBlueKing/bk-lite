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
