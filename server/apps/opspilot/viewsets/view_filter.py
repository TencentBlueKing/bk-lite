from django_filters import filters
from django_filters.rest_framework import FilterSet


class EnabledFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    is_enabled = filters.CharFilter(method="filter_is_enabled")

    @staticmethod
    def filter_is_enabled(queryset, name, value):  # noqa
        if not value:
            return queryset
        return queryset.filter(enabled=value == "1")
