# -- coding: utf-8 --
"""PC 发现采集的权威任务登记表。

每台 PC（按 inst_name）同一时间只有一个权威采集任务可以写入资产数据并执行删除；
显式移交期间 pending_task 可写不可删。不存凭据、不复制 PC 资产字段。
"""

from django.db import models

from apps.core.models.time_info import TimeInfo


class PCDiscoveryAuthority(TimeInfo):
    pc_inst_name = models.CharField(max_length=128, unique=True, help_text="PC 实例名（WIN-*/MAC-*）")
    authoritative_task = models.ForeignKey(
        "CollectModels", on_delete=models.PROTECT, related_name="owned_pcs", help_text="当前权威采集任务"
    )
    pending_task = models.ForeignKey(
        "CollectModels",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pending_pc_handovers",
        help_text="待移交任务（管理员已授权接管）",
    )
    last_snapshot_id = models.CharField(max_length=64, blank=True, default="", help_text="最近应用的快照 ID")
    last_snapshot_time = models.DateTimeField(null=True, blank=True, help_text="最近应用快照的采集时间")

    class Meta:
        db_table = "cmdb_pc_discovery_authority"
        verbose_name = "PC发现权威任务"
