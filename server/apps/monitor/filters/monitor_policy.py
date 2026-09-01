from django_filters import CharFilter, FilterSet

from apps.monitor.filters.id_filters import filter_positive_int_field
from apps.monitor.models.monitor_policy import MonitorPolicy


class MonitorPolicyFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object", lookup_expr="exact", label="监控对象", method="filter_monitor_object_id")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="策略名称")

    @staticmethod
    def filter_monitor_object_id(queryset, _name, value):
        return filter_positive_int_field(queryset, "monitor_object", value)

    class Meta:
        model = MonitorPolicy
        fields = ["monitor_object_id", "name"]
