from django_filters import FilterSet, CharFilter, BooleanFilter

from apps.monitor.models.monitor_condition import MonitorCondition


class MonitorConditionFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="条件名称")
    is_active = BooleanFilter(field_name="is_active", label="是否启用")

    class Meta:
        model = MonitorCondition
        fields = ["name", "is_active"]
