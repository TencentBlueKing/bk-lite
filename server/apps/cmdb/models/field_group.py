# -- coding: utf-8 --
# @File: field_group.py
# @Time: 2026/1/4
# @Author: windyzhao

from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class FieldGroup(TimeInfo, MaintainerInfo):
    """
    模型字段分组配置表
    用于将模型的属性字段进行逻辑分组，支持分组排序和管理
    """

    model_id = models.CharField(
        max_length=100,
        db_index=True,
        verbose_name="模型ID",
        help_text="关联的模型ID"
    )
    group_name = models.CharField(
        max_length=200,
        verbose_name="分组名称",
        help_text="分组唯一标识，与attrs.attr_group关联"
    )
    order = models.IntegerField(
        default=0,
        verbose_name="排序序号",
        help_text="值越小越靠前，用于控制分组显示顺序"
    )
    is_collapsed = models.BooleanField(
        default=False,
        verbose_name="是否默认折叠",
        help_text="前端展示时是否默认折叠该分组"
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name="分组描述",
        help_text="分组的详细说明"
    )
    attr_orders = models.JSONField(
        default=list,
        blank=True,
        null=True,
        verbose_name="属性排序",
        help_text="该分组下属性的排序列表"
    )

    class Meta:
        db_table = "cmdb_field_group"
        unique_together = [("model_id", "group_name")]
        ordering = ["model_id", "order"]
        verbose_name = "字段分组"
        verbose_name_plural = "字段分组"
        indexes = [models.Index(fields=["model_id", "order"], name="idx_model_order")]

    def __str__(self):
        return f"{self.model_id} - {self.group_name} (order: {self.order})"

    def __repr__(self):
        return f"<FieldGroup: {self.model_id}.{self.group_name}>"
