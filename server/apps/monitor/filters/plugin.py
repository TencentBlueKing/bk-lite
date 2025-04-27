from django_filters import FilterSet, CharFilter

from apps.monitor.models import MonitorPlugin


class MonitorPluginFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object", lookup_expr="exact", label="监控对象")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="插件名称")

    class Meta:
        model = MonitorPlugin
        fields = ["monitor_object_id", "name"]
