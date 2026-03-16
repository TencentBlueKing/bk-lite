"""脚本模型"""

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import ScriptType


class Script(TimeInfo, MaintainerInfo):
    """
    脚本库

    支持参数化脚本，参数使用 Jinja2 模板语法：{{ param_name }}
    """

    name = models.CharField(max_length=128, verbose_name="脚本名称")
    description = models.TextField(blank=True, default="", verbose_name="描述")

    script_type = models.CharField(max_length=32, choices=ScriptType.CHOICES, default=ScriptType.SHELL, verbose_name="脚本类型")

    # 脚本内容，支持 Jinja2 模板语法
    content = models.TextField(verbose_name="脚本内容")

    # 参数定义 JSON 格式
    # [{
    #     "name": "param1",          # 参数名（用于Jinja2模板引用）
    #     "label": "参数1",            # 参数标签（显示名称）
    #     "description": "提示信息",   # 提示信息
    #     "default": "",              # 默认值
    #     "is_encrypted": false       # 是否加密
    # }]
    params = models.JSONField(default=list, verbose_name="参数定义")

    # 默认超时时间（秒）
    timeout = models.IntegerField(default=60, verbose_name="超时时间")

    # 组织归属
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    # 是否为内置脚本
    is_built_in = models.BooleanField(default=False, verbose_name="是否内置")

    class Meta:
        verbose_name = "脚本"
        verbose_name_plural = verbose_name
        db_table = "job_script"
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
