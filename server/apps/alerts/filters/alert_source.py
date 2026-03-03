# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.alert_source import AlertSource


class AlertSourceModelFilter(FilterSet):
    # inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    search = CharFilter(field_name="name", lookup_expr="icontains", label="名称")

    class Meta:
        model = AlertSource
        fields = ["search"]
