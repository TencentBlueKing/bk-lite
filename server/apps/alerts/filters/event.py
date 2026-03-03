# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.models import Event


class EventModelFilter(FilterSet):
    # inst_id = NumberFilter(field_name="inst_id", lookup_expr="exact", label="实例ID")
    title = CharFilter(field_name="title", lookup_expr="icontains", label="名称")
    description = CharFilter(field_name="description", lookup_expr="icontains", label="内容")
    event_id = CharFilter(field_name="event_id", lookup_expr="exact", label="事件ID")
    alert_id = CharFilter(method="filter_alert_id", label="告警ID")
    source_id = CharFilter(field_name="source__source_id", lookup_expr="exact", label="告警源ID")
    received_at_after = CharFilter(field_name="received_at", lookup_expr="gte", label="接收时间（起始）")
    received_at_before = CharFilter(field_name="received_at", lookup_expr="lte", label="接收时间（结束）")

    class Meta:
        model = Event
        fields = ["title", "description", "event_id", "alert_id", "source_id", "received_at_after",
                  "received_at_before"]

    @staticmethod
    def filter_alert_id(qs, field_name, value):
        """查询类型"""
        qs = qs.filter(alert__pk=int(value))
        return qs
