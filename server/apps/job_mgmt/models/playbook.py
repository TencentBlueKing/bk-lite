"""Playbook模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class Playbook(TimeInfo, MaintainerInfo):
    """
    Playbook库

    存储 Ansible Playbook 压缩包，执行时解压并运行
    """

    name = models.CharField(max_length=128, verbose_name="Playbook名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    # 文件存储信息（MinIO）
    file_name = models.CharField(max_length=256, verbose_name="文件名")
    file_key = models.CharField(max_length=512, verbose_name="文件Key")
    bucket_name = models.CharField(max_length=128, default="job-mgmt-files", verbose_name="存储桶")
    file_size = models.BigIntegerField(default=0, verbose_name="文件大小")

    # 入口文件（playbook 主文件路径，相对于解压目录）
    entry_file = models.CharField(max_length=256, default="main.yml", verbose_name="入口文件")

    # 参数定义
    # [{"name": "param1", "label": "参数1", "type": "string", "default": "", "required": true}]
    params = models.JSONField(default=list, verbose_name="参数定义")

    # 默认超时时间（秒）
    timeout = models.IntegerField(default=300, verbose_name="超时时间")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    # 是否为预置
    is_preset = models.BooleanField(default=False, verbose_name="是否预置")

    class Meta:
        verbose_name = "Playbook"
        verbose_name_plural = verbose_name
        db_table = "job_playbook"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
