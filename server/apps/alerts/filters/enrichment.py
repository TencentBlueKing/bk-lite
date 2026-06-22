# -- coding: utf-8 --
from django_filters import FilterSet, CharFilter, BooleanFilter

from apps.alerts.models.enrichment import EnrichmentRule


class EnrichmentRuleModelFilter(FilterSet):
    name = CharFilter(field_name="name", lookup_expr="icontains", label="名称")
    provider_type = CharFilter(field_name="provider_type", lookup_expr="exact", label="数据源类型")
    is_active = BooleanFilter(field_name="is_active", label="是否启用")

    class Meta:
        model = EnrichmentRule
        fields = ["name", "provider_type", "is_active"]
