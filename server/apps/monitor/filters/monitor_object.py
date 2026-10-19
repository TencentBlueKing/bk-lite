from django_filters import CharFilter, FilterSet, NumberFilter

from apps.monitor.filters.id_filters import filter_positive_int_field
from apps.monitor.models.monitor_object import MonitorObject, MonitorObjectOrganizationRule
from apps.monitor.services.weopsx_cloud_catalog import CLOUD_FAMILY_TYPE_IDS


class MonitorObjectFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="指标对象名称")
    type = CharFilter(label="指标对象类型", required=False, method="filter_type")
    parent = NumberFilter(field_name="parent", lookup_expr="exact", label="父对象ID")

    def filter_type(self, queryset, _name, value):
        """点统一「云」时一次返回 Cloud / Tencent Cloud / Aliyun Cloud 平台对象。"""
        if not value:
            return queryset
        type_ids = CLOUD_FAMILY_TYPE_IDS if value in CLOUD_FAMILY_TYPE_IDS else (value,)
        return queryset.filter(type_id__in=type_ids)

    class Meta:
        model = MonitorObject
        fields = ["name", "type", "parent"]


class MonitorObjectOrganizationRuleFilter(FilterSet):
    monitor_object_id = CharFilter(field_name="monitor_object_id", lookup_expr="exact", label="监控对象id", method="filter_monitor_object_id")
    name = CharFilter(field_name="name", lookup_expr="icontains", label="分组规则名称")

    @staticmethod
    def filter_monitor_object_id(queryset, _name, value):
        return filter_positive_int_field(queryset, "monitor_object_id", value)

    class Meta:
        model = MonitorObjectOrganizationRule
        fields = ["monitor_object_id", "name"]
