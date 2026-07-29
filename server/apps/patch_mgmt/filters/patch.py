"""补丁库过滤器"""

from django.db.models import Count, Q
from django_filters import rest_framework as filters

from apps.patch_mgmt.models import Patch


class PatchFilter(filters.FilterSet):
    """补丁过滤器

    支持按补丁主记录字段过滤，同时支持跨 Windows/Linux detail 的通用名称/版本/架构过滤。
    """

    title = filters.CharFilter(field_name="title", lookup_expr="icontains")
    os_type = filters.CharFilter(field_name="os_type", lookup_expr="exact")
    patch_type = filters.CharFilter(field_name="patch_type", lookup_expr="exact")
    severity = filters.CharFilter(field_name="severity", lookup_expr="exact")
    pkg_status = filters.CharFilter(field_name="pkg_status", lookup_expr="exact")
    source_isnull = filters.BooleanFilter(method="filter_source_isnull")
    released_at_after = filters.DateTimeFilter(field_name="released_at", lookup_expr="gte")
    released_at_before = filters.DateTimeFilter(field_name="released_at", lookup_expr="lte")

    # 通用搜索：匹配标题、Windows KB 号或 Linux 包名
    search = filters.CharFilter(method="filter_search")
    # 通用名称：Windows KB 号 / Linux 包名
    name = filters.CharFilter(method="filter_name")
    # 通用版本/发行版：Windows 适用产品 / Linux 发行版
    version = filters.CharFilter(method="filter_version")
    # 架构：Windows / Linux detail 中的 architectures 数组
    arch = filters.CharFilter(method="filter_arch")

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(title__icontains=value)
            | Q(windows_detail__kb_number__icontains=value)
            | Q(linux_detail__pkg_name__icontains=value)
        )

    def filter_name(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(windows_detail__kb_number__icontains=value)
            | Q(linux_detail__pkg_name__icontains=value)
        )

    def filter_version(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(windows_detail__product_list__icontains=value)
            | Q(linux_detail__distro_name__icontains=value)
        )

    def filter_arch(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(windows_detail__architectures__contains=value)
            | Q(linux_detail__architectures__contains=value)
        )

    def filter_source_isnull(self, queryset, name, value):
        """M2M 后按 sources 是否为空过滤：True=手动(无来源)，False=自动(有来源)。"""
        if value is None:
            return queryset
        queryset = queryset.annotate(_src_count=Count("sources"))
        if value:
            return queryset.filter(_src_count=0)
        return queryset.filter(_src_count__gt=0)

    class Meta:
        model = Patch
        fields = [
            "title",
            "os_type",
            "patch_type",
            "severity",
            "pkg_status",
            "source_isnull",
            "search",
            "name",
            "version",
            "arch",
        ]
