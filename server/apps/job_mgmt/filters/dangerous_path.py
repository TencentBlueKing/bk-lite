"""高危路径过滤器"""

import django_filters

from apps.job_mgmt.models import DangerousPath


class DangerousPathFilter(django_filters.FilterSet):
    """高危路径过滤器"""

    level = django_filters.CharFilter(field_name="level", lookup_expr="exact")
    is_enabled = django_filters.BooleanFilter(field_name="is_enabled")

    class Meta:
        model = DangerousPath
        fields = ["level", "is_enabled"]
