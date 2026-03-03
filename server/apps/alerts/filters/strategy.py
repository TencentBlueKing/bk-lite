# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.alert_operator import AlarmStrategy


class AlarmStrategyModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="规则名称")
    created_at_after = CharFilter(field_name="created_at", lookup_expr="gte", label="创建时间（起始）")
    created_at_before = CharFilter(field_name="created_at", lookup_expr="lte", label="创建时间（结束）")

    class Meta:
        model = AlarmStrategy
        fields = ["name", "created_at_after", "created_at_before"]
