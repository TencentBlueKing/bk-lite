from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class MemorySpace(MaintainerInfo, TimeInfo):
    """记忆空间模型"""

    SCOPE_PERSONAL = "personal"
    SCOPE_TEAM = "team"
    SCOPE_CHOICES = [
        (SCOPE_PERSONAL, "个人"),
        (SCOPE_TEAM, "团队"),
    ]

    name = models.CharField(max_length=100, db_index=True, verbose_name=_("名称"))
    introduction = models.TextField(blank=True, default="", verbose_name=_("简介"))
    team = models.JSONField(default=list)
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_TEAM,
        verbose_name=_("可见范围"),
    )
    write_rule = models.TextField(blank=True, default="", verbose_name=_("写入规则"))
    default_model = models.CharField(max_length=100, blank=True, default="", verbose_name=_("默认模型"))

    class Meta:
        db_table = "memory_mgmt_memoryspace"
        verbose_name = "记忆空间"
        verbose_name_plural = "记忆空间"

    def __str__(self):
        return self.name


class Memory(MaintainerInfo, TimeInfo):
    """记忆条目模型

    个人记忆：owner_username + owner_domain 确定唯一用户，每个用户在每个记忆空间只有一条记忆
    组织记忆：organization_id 确定唯一组织，每个组织在每个记忆空间只有一条记忆
             owner_username 存储组织名称（用于显示）
    """

    memory_space = models.ForeignKey(
        MemorySpace,
        on_delete=models.CASCADE,
        related_name="memories",
        verbose_name=_("记忆空间"),
    )
    title = models.CharField(max_length=255, db_index=True, verbose_name=_("标题"))
    content = models.TextField(verbose_name=_("内容"))
    owner_username = models.CharField(max_length=150, verbose_name=_("创建者用户名/组织名"), db_index=True)
    owner_domain = models.CharField(max_length=255, verbose_name=_("创建者域"), db_index=True, blank=True, default="")
    organization_id = models.IntegerField(verbose_name=_("组织ID"), db_index=True, null=True, blank=True)

    class Meta:
        db_table = "memory_mgmt_memory"
        verbose_name = "记忆"
        verbose_name_plural = "记忆"
        indexes = [
            models.Index(fields=["owner_username", "owner_domain"]),
            models.Index(fields=["organization_id"]),
        ]

    def __str__(self):
        return self.title
