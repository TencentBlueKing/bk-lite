from django_filters import FilterSet, CharFilter

from apps.monitor.models.monitor_policy import MonitorPolicy


class MonitorPolicyFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object", lookup_expr="exact", label="监控对象")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="策略名称")

    class Meta:
        model = MonitorPolicy
        fields = ["monitor_object_id", "name"]
