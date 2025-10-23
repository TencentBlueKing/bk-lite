# -*- coding: utf-8 -*-
"""
基础设施实例模型
基于基础设施镜像启动的运行实例
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo
from apps.core.models.maintainer_info import MaintainerInfo
from .lab_image import LabImage


class InfraInstance(TimeInfo, MaintainerInfo):
    """
    基础设施实例模型
    基于 LabImage 启动的具体实例
    """
    
    STATUS_CHOICES = [
        ("stopped", _("已停止")),
        ("starting", _("启动中")),
        ("running", _("运行中")),
        ("stopping", _("停止中")),
        ("error", _("错误")),
    ]
    
    # 基本信息
    image = models.ForeignKey(
        LabImage,
        on_delete=models.CASCADE,
        verbose_name=_("基础设施镜像"),
        related_name="instances",
        limit_choices_to={'image_type': 'infra'}  # 限制只能选择基础设施镜像
    )
    name = models.CharField(_("实例名称"), max_length=100)
    status = models.CharField(_("运行状态"), max_length=20, choices=STATUS_CHOICES, default="stopped")
    endpoint = models.CharField(_("访问端点"), max_length=200, blank=True, null=True)
    
    # 容器运行时配置
    env_vars = models.JSONField(_("环境变量"), default=dict, help_text=_("容器运行时的环境变量，会覆盖镜像默认配置"))
    command = models.JSONField(_("启动命令"), default=list, blank=True, help_text=_("覆盖镜像的 CMD，为空则使用镜像默认值"))
    args = models.JSONField(_("启动参数"), default=list, blank=True, help_text=_("传递给启动命令的参数"))
    
    # 网络配置
    port_mappings = models.JSONField(_("端口映射"), default=dict, help_text=_("容器端口到宿主机端口的映射，格式: {'8080': '30080'}"))
    
    # 存储配置
    volume_mounts = models.JSONField(_("卷挂载"), default=list, help_text=_("持久化卷挂载配置，格式: [{'host_path': '/data', 'container_path': '/app/data', 'read_only': false}]"))
    persistent_dirs = models.JSONField(_("持久化目录"), default=list, help_text=_("需要持久化的容器内目录路径"))
    
    # 资源限制
    cpu_limit = models.CharField(_("CPU限制"), max_length=20, blank=True, null=True, help_text=_("如: '1', '0.5', '2'"))
    memory_limit = models.CharField(_("内存限制"), max_length=20, blank=True, null=True, help_text=_("如: '1Gi', '512Mi'"))
    
    # 额外参数（预留扩展）
    extra_params = models.JSONField(_("额外参数"), default=dict, help_text=_("其他容器启动参数"))
    
    class Meta:
        verbose_name = _("基础设施实例")
        verbose_name_plural = _("基础设施实例")
        unique_together = ("name",)  # 实例名称全局唯一
        
    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"