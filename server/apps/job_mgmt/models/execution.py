"""作业执行相关模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import ExecutionStatus, JobType, OverwriteStrategy, ScriptType, TargetSource, TriggerSource
from apps.job_mgmt.models.playbook import Playbook
from apps.job_mgmt.models.script import Script


class JobExecution(TimeInfo, MaintainerInfo):
    """
    作业执行记录

    记录每次作业执行的主记录
    """

    name = models.CharField(max_length=256, verbose_name="作业名称")

    job_type = models.CharField(max_length=32, choices=JobType.CHOICES, verbose_name="作业类型")
    trigger_source = models.CharField(max_length=32, choices=TriggerSource.CHOICES, default=TriggerSource.MANUAL, verbose_name="触发来源")
    status = models.CharField(max_length=32, choices=ExecutionStatus.CHOICES, default=ExecutionStatus.PENDING, verbose_name="执行状态")

    # 关联的脚本/Playbook（可为空，快速执行场景）
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联脚本")
    playbook = models.ForeignKey(Playbook, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联Playbook")

    # 目标来源
    target_source = models.CharField(max_length=32, choices=TargetSource.CHOICES, default=TargetSource.MANUAL, verbose_name="目标来源")

    # 目标列表（JSONField 存储）
    # node_mgmt 来源: [{"node_id": "xxx", "name": "xxx", "ip": "1.2.3.4", "os": "linux", "cloud_region_id": 1}]
    # manual 来源: [{"target_id": 1, "name": "xxx", "ip": "1.2.3.4"}]
    target_list = models.JSONField(default=list, verbose_name="目标列表")

    # 执行结果（每个目标的执行结果）
    execution_results = models.JSONField(default=list, verbose_name="执行结果")

    # 执行参数（脚本/Playbook 的参数值）
    params = models.TextField(blank=True, default="", verbose_name="执行参数")

    # 脚本执行专用字段
    script_type = models.CharField(max_length=32, choices=ScriptType.CHOICES, blank=True, default="", verbose_name="脚本类型")
    script_content = models.TextField(blank=True, default="", verbose_name="脚本内容")

    # 文件分发专用字段
    # [{"name": "app.tar.gz", "size": 1024000, "file_key": "xxx", "bucket_name": "job-mgmt-files"}]
    files = models.JSONField(default=list, verbose_name="分发文件列表")
    target_path = models.CharField(max_length=512, blank=True, default="", verbose_name="目标路径")
    overwrite_strategy = models.CharField(max_length=32, choices=OverwriteStrategy.CHOICES, default=OverwriteStrategy.OVERWRITE, verbose_name="覆盖策略")

    # 超时设置
    timeout = models.IntegerField(default=600, verbose_name="超时时间")

    # 执行时间
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    # 统计信息
    total_count = models.IntegerField(default=0, verbose_name="总目标数")
    success_count = models.IntegerField(default=0, verbose_name="成功数")
    failed_count = models.IntegerField(default=0, verbose_name="失败数")

    # 执行用户（快照，记录执行时的凭据用户名）
    executor_user = models.CharField(max_length=128, blank=True, default="", verbose_name="执行用户")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "作业执行"
        verbose_name_plural = verbose_name
        db_table = "job_execution"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}({self.get_status_display()})"
