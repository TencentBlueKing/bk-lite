# -- coding: utf-8 --
# @File: datasource_filters.py
# @Time: 2025/11/3 15:53
# @Author: windyzhao
from django.db.models import Q
from django_filters import CharFilter, FilterSet

from apps.operation_analysis.filters.base_filters import BaseGroupFilter
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace


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
    search = CharFilter(method="filter_search", label="名称/REST API")
    tags = CharFilter(method="filter_tags", label="标签名称")
    chart_type = CharFilter(method="filter_chart_type", label="图表类型")

    class Meta:
        model = DataSourceAPIModel
        fields = ["search", "tags"]

    @staticmethod
    def filter_tags(queryset, name, value):
        ids = value.split(",")
        return queryset.filter(tag__id__in=ids)

    @staticmethod
    def filter_search(queryset, name, value):
        keyword = (value or "").strip()
        if not keyword:
            return queryset
        return queryset.filter(Q(name__icontains=keyword) | Q(rest_api__icontains=keyword))

    @staticmethod
    def filter_chart_type(queryset, name, value):
        chart_types = [item.strip() for item in (value or "").split(",") if item.strip()]
        if not chart_types:
            return queryset

        query = Q()
        for chart_type in chart_types:
            query |= Q(chart_type__contains=[chart_type])
        return queryset.filter(query)
