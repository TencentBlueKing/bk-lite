from django_filters import rest_framework as filters
from apps.log.models.log_group import LogGroup, SearchCondition


class LogGroupFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    description = filters.CharFilter(field_name="description", lookup_expr="icontains")
    rule = filters.CharFilter(field_name="rule", lookup_expr="icontains")

    class Meta:
        model = LogGroup
        fields = ["name", "description", "rule"]


class SearchConditionFilter(filters.FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    created_by = filters.CharFilter(field_name="created_by", lookup_expr="icontains")

    class Meta:
        model = SearchCondition
        fields = ["name", "created_by"]