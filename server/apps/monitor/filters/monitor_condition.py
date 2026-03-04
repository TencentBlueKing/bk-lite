from django_filters import FilterSet, CharFilter, BooleanFilter

from apps.monitor.models.monitor_condition import MonitorCondition


class MonitorConditionFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="条件名称")
    is_active = BooleanFilter(field_name="is_active", label="是否启用")
    monitor_object_id = CharFilter(
        field_name="monitor_object_id", lookup_expr="exact", label="监控对象ID"
    )

    class Meta:
        model = MonitorCondition
        fields = ["name", "is_active", "monitor_object_id"]
