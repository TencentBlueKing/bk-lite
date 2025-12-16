from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class CustomMenuGroup(MaintainerInfo, TimeInfo):
    """
    自定义菜单组模型
    每个应用可以有多个菜单组，但只能启用一个
    menus 字段存储完整的菜单树结构（JSON格式）
    """

    # 显示名称
    display_name = models.CharField(max_length=100, verbose_name="显示名称")

    # 所属应用
    app = models.CharField(max_length=50, verbose_name="所属应用")

    # 启用状态（每个 app 只能启用一个）
    is_enabled = models.BooleanField(default=False, verbose_name="是否启用")

    # 是否内置
    is_build_in = models.BooleanField(default=False, verbose_name="是否内置")

    # 菜单配置（JSON格式存储菜单树）
    # 格式: [
    #   {
    #     "display_name": "一级菜单名称",
    #     "icon": "icon-class",
    #     "order": 0,
    #     "children": [
    #       {
    #         "display_name": "二级菜单名称",
    #         "icon": "icon-class",
    #         "order": 0,
    #         "menu_id": 1  # 关联的 Menu 表 ID
    #       }
    #     ]
    #   }
    # ]
    menus = models.JSONField(default=list, blank=True, verbose_name="菜单配置")

    # 描述
    description = models.TextField(null=True, blank=True, verbose_name="描述")

    class Meta:
        db_table = "system_mgmt_custom_menu_group"
        verbose_name = "自定义菜单组"
        verbose_name_plural = verbose_name
        # 同一个 app 下，显示名称不能重复
        unique_together = [("app", "display_name")]
        ordering = ["app", "id"]
        indexes = [
            models.Index(fields=["app"]),
            models.Index(fields=["app", "is_enabled"]),
        ]

    def __str__(self):
        return f"{self.app} - {self.display_name}"

    def clean(self):
        """数据校验"""
        # 如果要启用此菜单组，检查同一 app 下是否已有启用的菜单组
        if self.is_enabled:
            existing_enabled = CustomMenuGroup.objects.filter(app=self.app, is_enabled=True).exclude(id=self.id)

            if existing_enabled.exists():
                raise ValidationError(f"应用 {self.app} 已有启用的菜单组，每个应用只能启用一个菜单组")

    def save(self, *args, **kwargs):
        # 保存前执行校验
        self.clean()
        super().save(*args, **kwargs)
