# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.operator_log import OperatorLog


class OperatorLogModelFilter(FilterSet):
    operator = CharFilter(field_name="operator", lookup_expr="icontains", label="操作人")
    action = CharFilter(field_name="action", lookup_expr="exact", label="操作类型")
    overview = CharFilter(field_name="overview", lookup_expr="icontains", label="操作概述")
    target_id = CharFilter(field_name="target_id", lookup_expr="exact", label="目标ID")
    operator_object = CharFilter(field_name="operator_object", lookup_expr="exact", label="操作对象")
    created_at_after = CharFilter(field_name="created_at", lookup_expr="gte", label="创建时间（起始）")
    created_at_before = CharFilter(field_name="created_at", lookup_expr="lte", label="创建时间（结束）")

    class Meta:
        model = OperatorLog
        fields = ["operator", "action", "overview", "created_at_after", "created_at_before"]
