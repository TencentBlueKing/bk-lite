# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.alert_operator import AlertAssignment, AlertShield


class AlertAssignmentModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = AlertAssignment
        fields = ["name"]


class AlertShieldModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = AlertShield
        fields = ["name"]
