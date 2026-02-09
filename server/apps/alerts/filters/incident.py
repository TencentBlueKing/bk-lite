# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter

from apps.alerts.models.models import Incident


class IncidentModelFilter(FilterSet):
    title = CharFilter(field_name="title", lookup_expr="icontains", label="标题")
    incident_id = CharFilter(field_name="incident_id", lookup_expr="exact", label="事故ID")
    level = CharFilter(method="filter_level", label="告警级别")
    status = CharFilter(method="filter_status", label="告警状态")

    class Meta:
        model = Incident
        fields = ["title", "level", "status", "incident_id"]

    @staticmethod
    def filter_level(qs, field_name, value):
        """支持多选的告警级别过滤"""
        if value:
            # 支持逗号分隔的多个值
            levels = [level.strip() for level in value.split(',')]
            return qs.filter(level__in=levels)
        return qs

    @staticmethod
    def filter_status(qs, field_name, value):
        """支持多选的告警状态过滤"""
        if value:
            # 支持逗号分隔的多个值
            statuses = [status.strip() for status in value.split(',')]
            return qs.filter(status__in=statuses)
        return qs
