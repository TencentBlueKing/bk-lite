# -- coding: utf-8 --
# @File: filters.py
# @Time: 2025/7/14 16:02
# @Author: windyzhao

from django_filters import FilterSet, CharFilter

from apps.operation_analysis.models import DataSourceAPIModel, Dashboard, Directory, Topology, NameSpace, DataSourceTag, Architecture


class DataSourceAPIModelFilter(FilterSet):
    search = CharFilter(field_name="name", lookup_expr="icontains", label="名称")
    tags = CharFilter(method="filter_tags", label="标签名称")

    class Meta:
        model = DataSourceAPIModel
        fields = ["search", "tags"]

    @staticmethod
    def filter_tags(queryset, name, value):
        ids = value.split(",")
        return queryset.filter(tag__id__in=ids)


class DashboardModelFilter(FilterSet):
    search = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Dashboard
        fields = ["search"]


class DirectoryModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Directory
        fields = ["name"]


class TopologyModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Topology
        fields = ["name"]


class ArchitectureModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Architecture
        fields = ["name"]


class NameSpaceModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = NameSpace
        fields = ["name"]


class DataSourceTagModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = DataSourceTag
        fields = ["name"]
