from django_filters import FilterSet, CharFilter, BooleanFilter, NumberFilter

from apps.mlops.models import AlgorithmConfig


class AlgorithmConfigFilter(FilterSet):
    """算法配置过滤器"""

    algorithm_type = CharFilter(
        field_name="algorithm_type", lookup_expr="exact", label="算法类型"
    )
    name = CharFilter(field_name="name", lookup_expr="icontains", label="算法标识")
    display_name = CharFilter(
        field_name="display_name", lookup_expr="icontains", label="显示名称"
    )
    is_active = BooleanFilter(field_name="is_active", label="是否启用")
    created_by = CharFilter(
        field_name="created_by", lookup_expr="icontains", label="创建者"
    )

    class Meta:
        model = AlgorithmConfig
        fields = ["algorithm_type", "name", "display_name", "is_active", "created_by"]
