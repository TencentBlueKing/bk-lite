from django.db.models import Q
from django_filters import BaseInFilter, BooleanFilter, CharFilter, FilterSet, NumberFilter

from apps.monitor.models.monitor_metrics import Metric, MetricGroup


class MetricGroupFilter(FilterSet):
    monitor_object_name = CharFilter(field_name="monitor_object__name", lookup_expr="exact", label="指标对象名称")
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="指标对象ID")
    monitor_plugin_id = CharFilter(field_name="monitor_plugin_id", lookup_expr="exact", label="插件ID")
    name = CharFilter(field_name="name", lookup_expr="exact", label="指标分组名称")
    keyword = CharFilter(method="filter_keyword", label="指标分组关键字")

    @staticmethod
    def filter_keyword(queryset, _name, value):
        keyword = str(value or "").strip()
        if not keyword:
            return queryset
        return queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))

    class Meta:
        model = MetricGroup
        fields = ["monitor_object_name", "monitor_object_id", "monitor_plugin_id", "name", "keyword"]


class NumberInFilter(BaseInFilter, NumberFilter):
    pass


class CharInFilter(BaseInFilter, CharFilter):
    pass


class MetricFilter(FilterSet):
    monitor_object_name = CharFilter(field_name="monitor_object__name", lookup_expr="exact", label="指标对象名称")
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="指标对象ID")
    monitor_plugin_id = CharFilter(field_name="monitor_plugin_id", lookup_expr="exact", label="插件ID")
    id = NumberFilter(field_name="id", lookup_expr="exact", label="指标ID")
    id_in = NumberInFilter(field_name="id", lookup_expr="in", label="指标ID列表")
    name = CharFilter(field_name="name", lookup_expr="exact", label="指标名称")
    name_in = CharInFilter(field_name="name", lookup_expr="in", label="指标名称列表")
    keyword = CharFilter(method="filter_keyword", label="指标关键字")
    include_ifmib = BooleanFilter(method="filter_include_ifmib", label="是否包含IF-MIB指标")
    is_ifmib = BooleanFilter(field_name="is_ifmib", label="是否为IF-MIB指标")

    @staticmethod
    def filter_keyword(queryset, _name, value):
        keyword = str(value or "").strip()
        if not keyword:
            return queryset
        return queryset.filter(
            Q(name__icontains=keyword)
            | Q(display_name__icontains=keyword)
            | Q(description__icontains=keyword)
        )

    @staticmethod
    def filter_include_ifmib(queryset, _name, value):
        if value is False:
            return queryset.filter(is_ifmib=False)
        return queryset

    class Meta:
        model = Metric
        fields = [
            "monitor_object_name",
            "monitor_object_id",
            "monitor_plugin_id",
            "id",
            "id_in",
            "name",
            "name_in",
            "keyword",
            "include_ifmib",
            "is_ifmib",
        ]
