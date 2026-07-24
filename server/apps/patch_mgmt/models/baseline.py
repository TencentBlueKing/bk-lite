"""基线管理模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.patch_mgmt.constants import ComplianceStatus, OSType


class PatchBaseline(TimeInfo, MaintainerInfo):
    """补丁基线

    固定清单基线，包含若干补丁要求。一台主机绑定一个基线。
    MVP 不做版本管理，基线只有当前清单，无历史版本快照。
    有进行中治理任务时禁止修改。
    """

    name = models.CharField(max_length=128, verbose_name="基线名称")
    os_type = models.CharField(
        max_length=16,
        choices=OSType.CHOICES,
        verbose_name="OS 类型",
    )
    description = models.TextField(blank=True, default="", verbose_name="说明")
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        db_table = "patch_baseline"
        verbose_name = "补丁基线"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class BaselineRequirement(TimeInfo):
    """基线补丁要求

    表达"主机必须达到的状态"：
    - Windows：装该 KB 或有效替代 KB
    - Linux：包版本 ≥ 最低版本要求
    """

    baseline = models.ForeignKey(
        PatchBaseline,
        on_delete=models.CASCADE,
        related_name="requirements",
        verbose_name="所属基线",
    )
    patch = models.ForeignKey(
        "patch_mgmt.Patch",
        on_delete=models.PROTECT,
        related_name="baseline_requirements",
        verbose_name="关联补丁",
    )
    condition = models.CharField(
        max_length=256,
        blank=True,
        default="",
        verbose_name="满足条件",
    )

    class Meta:
        db_table = "patch_baseline_requirement"
        verbose_name = "基线补丁要求"
        verbose_name_plural = verbose_name
        unique_together = (("baseline", "patch"),)

    def __str__(self):
        return f"{self.baseline.name} - {self.patch_id}"


class HostBaselineBinding(TimeInfo, MaintainerInfo):
    """主机基线绑定

    一台主机同时最多绑定一个基线，也允许未绑定。
    持久化最近一次评估结果，避免每次都重算全量风险。
    """

    target = models.OneToOneField(
        "patch_mgmt.PatchTarget",
        on_delete=models.CASCADE,
        related_name="baseline_binding",
        verbose_name="目标主机",
    )
    baseline = models.ForeignKey(
        PatchBaseline,
        on_delete=models.CASCADE,
        related_name="host_bindings",
        verbose_name="绑定的基线",
    )
    # 最近一次评估结果（异步任务写回）
    compliance_status = models.CharField(
        max_length=32,
        choices=ComplianceStatus.CHOICES,
        default=ComplianceStatus.PENDING,
        verbose_name="合规状态",
    )
    last_evaluated_at = models.DateTimeField(null=True, blank=True, verbose_name="最后评估时间")
    last_detected_at = models.DateTimeField(null=True, blank=True, verbose_name="最后连通性检测时间")
    missing_count = models.IntegerField(default=0, verbose_name="缺失补丁数")
    pending_reboot_count = models.IntegerField(default=0, verbose_name="待重启补丁数")

    class Meta:
        db_table = "patch_host_baseline_binding"
        verbose_name = "主机基线绑定"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.target_id} -> {self.baseline.name}"


class HostComplianceSnapshot(TimeInfo):
    """主机基线合规快照

    记录某次评估任务后，主机针对基线每条要求的满足情况。
    每次新的 assess 任务成功后会替换该 binding 下的全部快照。
    """

    binding = models.ForeignKey(
        HostBaselineBinding,
        on_delete=models.CASCADE,
        related_name="compliance_snapshots",
        verbose_name="主机基线绑定",
    )
    requirement = models.ForeignKey(
        BaselineRequirement,
        on_delete=models.CASCADE,
        related_name="compliance_snapshots",
        verbose_name="基线要求",
    )
    satisfied = models.BooleanField(default=False, verbose_name="是否满足")
    evidence = models.JSONField(default=dict, verbose_name="满足证据")
    reason = models.TextField(blank=True, default="", verbose_name="原因说明")
    evaluated_at = models.DateTimeField(verbose_name="评估时间")

    class Meta:
        db_table = "patch_host_compliance_snapshot"
        verbose_name = "主机合规快照"
        verbose_name_plural = verbose_name
        unique_together = (("binding", "requirement"),)

    def __str__(self):
        return f"{self.binding_id} -> {self.requirement_id}: {'满足' if self.satisfied else '不满足'}"
