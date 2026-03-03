from django.db import models
from django.utils.translation import gettext_lazy as _


class UserPersonalConfig(models.Model):
    """用户个人配置 - 通用配置系统
    
    支持多种配置类型的统一管理：
    - search_inst_{model_id}: 模型实例搜索收藏配置
    - search_model: 模型搜索配置
    - table_columns_{model_id}: 表格列显示配置
    - dashboard_layout: 仪表板布局
    等等...
    """

    username = models.CharField(
        max_length=255, verbose_name=_("用户名"), db_index=True
    )
    domain = models.CharField(
        max_length=255, verbose_name=_("域名"), db_index=True
    )
    config_key = models.CharField(
        max_length=100, verbose_name=_("配置键"), db_index=True,
        help_text=_("配置类型标识，如: search_inst_{model_id}")
    )
    config_value = models.JSONField(
        default=dict, verbose_name=_("配置值")
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name=_("更新时间")
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("创建时间")
    )

    class Meta:
        verbose_name = _("用户个人配置")
        verbose_name_plural = _("用户个人配置")
        db_table = "cmdb_user_personal_config"
        unique_together = [["username", "domain", "config_key"]]
        indexes = [
            models.Index(fields=["username", "domain", "config_key"]),
            models.Index(fields=["username", "domain"]),
        ]

    def __str__(self):
        return f"{self.username}@{self.domain} - {self.config_key}"
