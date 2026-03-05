"""作业执行相关模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import ExecutionStatus, JobType, ScriptType
from apps.job_mgmt.models.playbook import Playbook
from apps.job_mgmt.models.script import Script
from apps.job_mgmt.models.target import Target


class JobExecution(TimeInfo, MaintainerInfo):
    """
    作业执行记录

    记录每次作业执行的主记录
    """

    name = models.CharField(max_length=256, verbose_name="作业名称")

    job_type = models.CharField(max_length=32, choices=JobType.CHOICES, verbose_name="作业类型")
    status = models.CharField(max_length=32, choices=ExecutionStatus.CHOICES, default=ExecutionStatus.PENDING, verbose_name="执行状态")

    # 关联的脚本/Playbook（可为空，快速执行场景）
    script = models.ForeignKey(Script, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联脚本")
    playbook = models.ForeignKey(Playbook, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="关联Playbook")

    # 执行目标
    targets = models.ManyToManyField(Target, through="JobExecutionTarget", verbose_name="执行目标")

    # 执行参数（脚本/Playbook 的参数值）
    params = models.JSONField(default=dict, verbose_name="执行参数")

    # 脚本执行专用字段
    script_type = models.CharField(max_length=32, choices=ScriptType.CHOICES, blank=True, default="", verbose_name="脚本类型")
    script_content = models.TextField(blank=True, default="", verbose_name="脚本内容")

    # 文件分发专用字段
    # [{"name": "app.tar.gz", "size": 1024000, "file_key": "xxx", "bucket_name": "job-mgmt-files"}]
    files = models.JSONField(default=list, verbose_name="分发文件列表")
    target_path = models.CharField(max_length=512, blank=True, default="", verbose_name="目标路径")

    # 超时设置
    timeout = models.IntegerField(default=60, verbose_name="超时时间")

    # 执行时间
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    # 统计信息
    total_count = models.IntegerField(default=0, verbose_name="总目标数")
    success_count = models.IntegerField(default=0, verbose_name="成功数")
    failed_count = models.IntegerField(default=0, verbose_name="失败数")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "作业执行"
        verbose_name_plural = verbose_name
        db_table = "job_execution"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}({self.get_status_display()})"


class JobExecutionTarget(TimeInfo):
    """
    作业执行目标明细

    记录每个目标的执行状态和结果
    """

    execution = models.ForeignKey(JobExecution, on_delete=models.CASCADE, related_name="execution_targets", verbose_name="作业执行")
    target = models.ForeignKey(Target, on_delete=models.CASCADE, verbose_name="执行目标")

    status = models.CharField(max_length=32, choices=ExecutionStatus.CHOICES, default=ExecutionStatus.PENDING, verbose_name="执行状态")

    # 执行结果
    stdout = models.TextField(blank=True, default="", verbose_name="标准输出")
    stderr = models.TextField(blank=True, default="", verbose_name="错误输出")
    exit_code = models.IntegerField(null=True, blank=True, verbose_name="退出码")

    # 执行时间
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    # 错误信息
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")

    class Meta:
        verbose_name = "作业执行目标"
        verbose_name_plural = verbose_name
        db_table = "job_execution_target"
        ordering = ["id"]
        unique_together = [["execution", "target"]]

    def __str__(self):
        return f"{self.execution.name}-{self.target.name}"


class FileDistributionItem(TimeInfo):
    """
    文件分发明细

    记录每个文件在每个目标上的分发状态
    """

    execution = models.ForeignKey(JobExecution, on_delete=models.CASCADE, related_name="file_items", verbose_name="作业执行")
    target = models.ForeignKey(Target, on_delete=models.CASCADE, verbose_name="执行目标")

    # 文件信息
    file_name = models.CharField(max_length=256, verbose_name="文件名")
    file_key = models.CharField(max_length=512, verbose_name="文件Key")
    bucket_name = models.CharField(max_length=128, default="", verbose_name="存储桶")
    file_size = models.BigIntegerField(default=0, verbose_name="文件大小")

    status = models.CharField(max_length=32, choices=ExecutionStatus.CHOICES, default=ExecutionStatus.PENDING, verbose_name="执行状态")

    # 执行时间
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="开始时间")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")

    # 错误信息
    error_message = models.TextField(blank=True, default="", verbose_name="错误信息")

    class Meta:
        verbose_name = "文件分发明细"
        verbose_name_plural = verbose_name
        db_table = "job_file_distribution_item"
        ordering = ["id"]

    def __str__(self):
        return f"{self.file_name}->{self.target.name}"
