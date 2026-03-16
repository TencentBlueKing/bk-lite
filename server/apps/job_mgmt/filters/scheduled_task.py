"""定时任务过滤器"""

import django_filters

from apps.job_mgmt.models import ScheduledTask


class ScheduledTaskFilter(django_filters.FilterSet):
    """定时任务过滤器"""

    name = django_filters.CharFilter(lookup_expr="icontains")
    job_type = django_filters.CharFilter()
    schedule_type = django_filters.CharFilter()
    is_enabled = django_filters.BooleanFilter()
    created_by = django_filters.CharFilter()
    created_at_after = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = django_filters.DateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = ScheduledTask
        fields = ["name", "job_type", "schedule_type", "is_enabled", "created_by"]
