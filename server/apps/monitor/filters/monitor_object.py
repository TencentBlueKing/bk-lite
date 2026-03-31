from django_filters import FilterSet, CharFilter, NumberFilter

from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectOrganizationRule


class MonitorObjectFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="指标对象名称")
    type = CharFilter(field_name="type", lookup_expr="exact", label="指标对象类型")
    parent = NumberFilter(field_name="parent", lookup_expr="exact", label="父对象ID")

    class Meta:
        model = MonitorObject
        fields = ["name", "type", "parent"]


class MonitorObjectOrganizationRuleFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="监控对象id")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="分组规则名称")

    class Meta:
        model = MonitorObjectOrganizationRule
        fields = ["monitor_object_id", "name"]
