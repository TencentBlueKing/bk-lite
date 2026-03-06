"""脚本过滤器"""

from django_filters import rest_framework as filters

from apps.job_mgmt.models import Script


class ScriptFilter(filters.FilterSet):
    """脚本过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    script_type = filters.CharFilter(field_name="script_type", lookup_expr="exact")
    os_type = filters.CharFilter(field_name="os_type", lookup_expr="exact")
    is_built_in = filters.BooleanFilter(field_name="is_built_in")

    class Meta:
        model = Script
        fields = ["name", "script_type", "is_built_in"]
