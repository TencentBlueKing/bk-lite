# -- coding: utf-8 --
# @File: datasource_filters.py
# @Time: 2025/11/3 15:53
# @Author: windyzhao
from django_filters import FilterSet, CharFilter

from apps.operation_analysis.filters.base_filters import BaseGroupFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace, DataSourceTag


class DataSourceTagModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = DataSourceTag
        fields = ["name"]


class NameSpaceModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = NameSpace
        fields = ["name"]


class DataSourceAPIModelFilter(BaseGroupFilter):
    search = CharFilter(field_name="name", lookup_expr="icontains", label="名称")
    tags = CharFilter(method="filter_tags", label="标签名称")

    class Meta:
        model = DataSourceAPIModel
        fields = ["search", "tags"]

    @staticmethod
    def filter_tags(queryset, name, value):
        ids = value.split(",")
        return queryset.filter(tag__id__in=ids)
