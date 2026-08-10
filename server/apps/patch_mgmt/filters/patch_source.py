"""补丁源过滤器"""

from django_filters import rest_framework as filters

from apps.patch_mgmt.models import PatchSource


class PatchSourceFilter(filters.FilterSet):
    """补丁源过滤器"""

    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    source_type = filters.CharFilter(field_name="source_type", lookup_expr="exact")
    is_enabled = filters.BooleanFilter(field_name="is_enabled")
    connectivity_status = filters.CharFilter(
        field_name="connectivity_status", lookup_expr="exact"
    )

    class Meta:
        model = PatchSource
        fields = ["name", "source_type", "is_enabled", "connectivity_status"]
