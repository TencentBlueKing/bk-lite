# -*- coding: utf-8 -*-
"""
Lab 环境模型
统一管理 IDE 和基础设施的实验环境
"""

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

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
    
    # 状态转移规则定义
    STATE_TRANSITIONS = {
        'stopped': ['starting'],
        'starting': ['running', 'stopping', 'error', 'stopped'],  # 允许启动中停止
        'running': ['stopping', 'error'],
        'stopping': ['stopped', 'error'],
        'error': ['starting', 'stopping', 'stopped'],
    }
    
    def can_transition_to(self, new_state):
        """
        检查是否可以从当前状态转移到新状态
        
        Args:
            new_state: 目标状态
            
        Returns:
            bool: 是否可以转移
        """
        allowed_states = self.STATE_TRANSITIONS.get(self.state, [])
        return new_state in allowed_states
    
    @transaction.atomic
    def transition_state(self, new_state, force=False):
        """
        安全地转移环境状态,带并发保护
        
        Args:
            new_state: 目标状态
            force: 是否强制转移(跳过状态规则检查)
            
        Returns:
            bool: 是否成功转移
            
        Raises:
            ValidationError: 状态转移不合法时
        """
        # 使用 select_for_update 锁定当前记录,防止并发修改
        locked_env = LabEnv.objects.select_for_update().get(pk=self.pk)
        
        # 验证状态转移是否合法(基于数据库中的实际状态)
        if not force and not locked_env.can_transition_to(new_state):
            raise ValidationError(
                f"无法从状态 '{locked_env.state}' 转移到 '{new_state}'. "
                f"允许的状态: {', '.join(self.STATE_TRANSITIONS.get(locked_env.state, []))}"
            )
        
        # 更新数据库状态
        locked_env.state = new_state
        locked_env.save(update_fields=['state', 'updated_at'])
        
        # 同步到当前实例(重要:必须刷新整个实例以保持一致)
        self.refresh_from_db()
        
        return True
    
    def safe_start(self):
        """安全地将状态设置为starting"""
        return self.transition_state('starting')
    
    def safe_stop(self):
        """安全地将状态设置为stopping"""
        return self.transition_state('stopping')
    
    def mark_running(self):
        """标记为运行中"""
        return self.transition_state('running')
    
    def mark_stopped(self):
        """标记为已停止"""
        return self.transition_state('stopped')
    
    def mark_error(self):
        """标记为错误状态(可以从任何状态转移)"""
        return self.transition_state('error', force=True)