from django_filters import FilterSet, CharFilter

from apps.monitor.models.monitor_object import MonitorObject, MonitorInstanceGroupingRule


class MonitorObjectFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="指标对象名称")
    type = CharFilter(field_name="type", lookup_expr="exact", label="指标对象类型")

    class Meta:
        model = MonitorObject
        fields = ["name", "type"]


class MonitorInstanceGroupingRuleFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="监控对象id")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="分组规则名称")


    class Meta:
        model = MonitorInstanceGroupingRule
        fields = ["monitor_object_id", "name"]
