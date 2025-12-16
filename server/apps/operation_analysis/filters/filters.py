# -- coding: utf-8 --
# @File: filters.py
# @Time: 2025/7/14 16:02
# @Author: windyzhao

from django_filters import CharFilter

from apps.operation_analysis.filters.base_filters import BaseGroupFilter
from apps.operation_analysis.models.models import Dashboard, Directory, Topology, Architecture


class DashboardModelFilter(BaseGroupFilter):
    search = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Dashboard
        fields = ["search"]


class DirectoryModelFilter(BaseGroupFilter):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Directory
        fields = ["name"]


class TopologyModelFilter(BaseGroupFilter):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Topology
        fields = ["name"]


class ArchitectureModelFilter(BaseGroupFilter):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = Architecture
        fields = ["name"]
