# -- coding: utf-8 --
# @File: field_group.py
# @Time: 2026/1/4
# @Author: windyzhao

from django_filters import CharFilter, FilterSet, NumberFilter, BooleanFilter

from apps.cmdb.models.field_group import FieldGroup


class FieldGroupFilter(FilterSet):
    """字段分组过滤器"""

    model_id = CharFilter(field_name="model_id", lookup_expr="exact", label="模型ID")
    group_name = CharFilter(
        field_name="group_name", lookup_expr="icontains", label="分组名称"
    )
    is_collapsed = BooleanFilter(
        field_name="is_collapsed", lookup_expr="exact", label="是否折叠"
    )
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建人"
    )

    class Meta:
        model = FieldGroup
        fields = ["model_id", "group_name", "is_collapsed", "created_by"]
