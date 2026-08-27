from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class SceneView(TimeInfo, MaintainerInfo):
    class Visibility:
        PERSONAL = "personal"
        ORGANIZATION = "organization"
        GLOBAL = "global"
        CHOICES = (
            (PERSONAL, "个人"),
            (ORGANIZATION, "组织共享"),
            (GLOBAL, "全局"),
        )

    class TagMatch:
        AND = "and"
        OR = "or"
        CHOICES = ((AND, "AND"), (OR, "OR"))

    name = models.CharField(max_length=128, verbose_name="视图名称")
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.CHOICES,
        default=Visibility.PERSONAL,
        db_index=True,
        verbose_name="可见范围",
    )
    organization = models.BigIntegerField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="组织共享所属组织ID",
    )
    model_ids = models.JSONField(default=list, verbose_name="模型范围")
    tags = models.JSONField(default=list, verbose_name="标签条件")
    tag_match = models.CharField(
        max_length=8,
        choices=TagMatch.CHOICES,
        default=TagMatch.AND,
        verbose_name="标签匹配",
    )

    class Meta:
        db_table = "cmdb_scene_view"
        verbose_name = "标签视图"
        verbose_name_plural = "标签视图"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["created_by", "domain", "visibility"], name="idx_scene_owner_vis"),
            models.Index(fields=["visibility", "organization"], name="idx_scene_vis_org"),
        ]

    def __str__(self):
        return f"SceneView({self.id}:{self.name})"
