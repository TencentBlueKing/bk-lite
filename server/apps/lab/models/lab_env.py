# -*- coding: utf-8 -*-
"""
Lab 环境模型
统一管理 IDE 和基础设施的实验环境
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo
from apps.core.models.maintainer_info import MaintainerInfo
from .lab_image import LabImage
from .infra_instance import InfraInstance


class LabEnv(TimeInfo, MaintainerInfo):
    """
    Lab 环境模型
    包含 IDE + 基础设施实例 + 资源配置的完整实验环境
    """
    
    STATE_CHOICES = [
        ("stopped", _("已停止")),
        ("starting", _("启动中")),
        ("running", _("运行中")),
        ("stopping", _("停止中")),
        ("error", _("错误")),
    ]
    
    name = models.CharField(_("环境名称"), max_length=100, unique=True)
    description = models.TextField(_("环境描述"), blank=True, null=True)
    
    # IDE 配置
    ide_image = models.ForeignKey(
        LabImage,
        on_delete=models.CASCADE,
        verbose_name=_("IDE镜像"),
        related_name="lab_envs",
        limit_choices_to={'image_type': 'ide'}  # 限制只能选择IDE镜像
    )
    
    # 基础设施实例（多对多关系）
    infra_instances = models.ManyToManyField(
        InfraInstance,
        verbose_name=_("基础设施实例"),
        related_name="lab_envs",
        blank=True
    )
    
    # 资源配置
    cpu = models.IntegerField(_("CPU核数"), default=2, help_text=_("CPU核心数量"))
    memory = models.CharField(_("内存大小"), max_length=20, default="4Gi", help_text=_("如: 4Gi, 8Gi"))
    gpu = models.IntegerField(_("GPU数量"), default=0, help_text=_("独占GPU数量"))
    volume_size = models.CharField(_("存储大小"), max_length=20, default="50Gi", help_text=_("持久化卷大小"))
    
    # 运行状态
    state = models.CharField(_("环境状态"), max_length=20, choices=STATE_CHOICES, default="stopped")
    endpoint = models.CharField(_("访问端点"), max_length=200, blank=True, null=True)
    
    class Meta:
        verbose_name = _("Lab环境")
        verbose_name_plural = _("Lab环境")
        
    def __str__(self):
        return f"Lab {self.name} ({self.get_state_display()})"