from django_filters import FilterSet, CharFilter

from apps.monitor.models import MonitorPlugin


class MonitorPluginFilter(FilterSet):
    monitor_object_id = CharFilter(
        field_name="monitor_object",
        lookup_expr="exact",
        label="监控对象",
        required=False,  # 设置为非必填
        method='filter_monitor_object'  # 使用自定义过滤方法
    )
    name = CharFilter(field_name="name", lookup_expr="icontains", label="插件名称")

    def filter_monitor_object(self, queryset, name, value):
        """自定义过滤方法：为空时返回全部，否则按监控对象ID过滤"""
        if value:
            return queryset.filter(monitor_object=value)
        return queryset

    class Meta:
        model = MonitorPlugin
        fields = ["monitor_object_id", "name"]
