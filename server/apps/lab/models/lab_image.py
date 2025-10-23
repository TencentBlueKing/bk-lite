# -*- coding: utf-8 -*-
"""
Lab 镜像模型
统一管理 IDE 和基础设施 Docker 镜像
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.time_info import TimeInfo
from apps.core.models.maintainer_info import MaintainerInfo


class LabImage(TimeInfo, MaintainerInfo):
    """
    Lab 镜像模型
    统一管理 IDE（JupyterLab、VSCode）和基础设施（数据库、中间件）的 Docker 镜像
    """
    
    IMAGE_TYPE_CHOICES = [
        ("ide", _("IDE镜像")),
        ("infra", _("基础设施镜像")),
    ]
    
    # 基本信息
    name = models.CharField(_("镜像名称"), max_length=100)
    version = models.CharField(_("镜像版本"), max_length=50)
    image_type = models.CharField(_("镜像类型"), max_length=20, choices=IMAGE_TYPE_CHOICES)
    description = models.TextField(_("镜像描述"), blank=True, null=True)
    
    # Docker 镜像配置
    image = models.CharField(_("容器镜像地址"), max_length=200)
    default_port = models.IntegerField(_("默认端口"), default=8888)
    default_env = models.JSONField(_("默认环境变量"), default=dict, help_text=_("容器启动时的环境变量"))
    default_command = models.JSONField(_("默认启动命令"), default=list, help_text=_("覆盖镜像的 CMD"))
    default_args = models.JSONField(_("默认启动参数"), default=list, help_text=_("传递给启动命令的参数"))
    
    # 额外配置
    expose_ports = models.JSONField(_("暴露端口列表"), default=list, help_text=_("需要暴露的端口号列表"))
    volume_mounts = models.JSONField(_("卷挂载配置"), default=list, help_text=_("预定义的卷挂载点"))
    
    class Meta:
        verbose_name = _("Lab镜像")
        verbose_name_plural = _("Lab镜像")
        unique_together = ("name", "version", "image_type")
        
    def __str__(self):
        return f"{self.get_image_type_display()}: {self.name}:{self.version}"
        
    @property
    def is_ide(self):
        """判断是否为 IDE 镜像"""
        return self.image_type == "ide"
        
    @property
    def is_infra(self):
        """判断是否为基础设施镜像"""
        return self.image_type == "infra"