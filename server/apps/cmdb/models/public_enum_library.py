# -- coding: utf-8 --
# @File: public_enum_library.py
# @Time: 2026/3/9
# @Author: windyzhao

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class PublicEnumLibrary(TimeInfo, MaintainerInfo):
    """
    公共选项库主表。

    用于维护跨模型共享的枚举选项集合。
    枚举字段可绑定公共选项库，实现选项集中管理与一致性维护。

    设计约束：
    1. options 结构固定为 [{"id": str, "name": str}]，服务层负责内容校验。
    2. 删除语义采用物理删除（hard delete）：若被字段引用则直接拦截，不进入删除。
    3. 不新增"引用关系表"，引用关系实时扫描模型 attrs（保持最小改动）。
    4. team 直接复用项目现有"关联组织"口径，不新增 include_subgroups 字段。
    5. library_id 全局唯一，name 非唯一（同名是否允许由服务层按业务规则校验）。
    """

    library_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        verbose_name="公共选项库ID",
        help_text="全局唯一标识，用于字段绑定引用",
    )
    name = models.CharField(
        max_length=128,
        db_index=True,
        verbose_name="公共选项库名称",
        help_text="显示名称，支持中英文",
    )
    team = models.JSONField(
        default=list,
        verbose_name="关联组织",
        help_text="关联的组织ID列表，用于权限控制",
    )
    options = models.JSONField(
        default=list,
        verbose_name="选项列表",
        help_text='枚举选项集合，结构为 [{"id": str, "name": str}]',
    )

    class Meta:
        db_table = "cmdb_public_enum_library"
        verbose_name = "公共选项库"
        verbose_name_plural = "公共选项库"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["library_id"], name="idx_public_enum_lib_id"),
            models.Index(fields=["name"], name="idx_public_enum_lib_name"),
        ]

    def __str__(self):
        return f"{self.name} ({self.library_id})"

    def __repr__(self):
        return f"<PublicEnumLibrary: {self.library_id}>"
