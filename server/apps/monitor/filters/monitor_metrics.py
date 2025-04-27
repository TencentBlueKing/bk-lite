from django_filters import CharFilter, FilterSet

from apps.monitor.models.monitor_metrics import MetricGroup, Metric


class MetricGroupFilter(FilterSet):
    monitor_object_name = CharFilter(field_name="monitor_object__name", lookup_expr="exact", label="指标对象名称")
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="指标对象ID")
    monitor_plugin_id = CharFilter(field_name="monitor_plugin_id", lookup_expr="exact", label="插件ID")

    class Meta:
        model = MetricGroup
        fields = ["monitor_object_name", "monitor_object_id", "monitor_plugin_id"]


class MetricFilter(FilterSet):
    monitor_object_name = CharFilter(field_name="monitor_object__name", lookup_expr="exact", label="指标对象名称")
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="指标对象ID")
    monitor_plugin_id = CharFilter(field_name="monitor_plugin_id", lookup_expr="exact", label="插件ID")

    class Meta:
        model = Metric
        fields = ["monitor_object_name", "monitor_object_id", "monitor_plugin_id"]
