"""危险规则过滤器"""

from django_filters import rest_framework as filters

from apps.job_mgmt.models import DangerousRule


class DangerousRuleFilter(filters.FilterSet):
    """危险规则过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    level = filters.CharFilter(field_name="level", lookup_expr="exact")
    is_enabled = filters.BooleanFilter(field_name="is_enabled")

    class Meta:
        model = DangerousRule
        fields = ["name", "level", "is_enabled"]
