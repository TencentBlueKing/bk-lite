from django_filters import rest_framework as filters
from apps.log.models import CollectType, CollectInstance, CollectConfig


class CollectTypeFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    collector = filters.CharFilter(lookup_expr='icontains')
    add_policy_count = filters.BooleanFilter(method='filter_add_policy_count')
    add_instance_count = filters.BooleanFilter(method='filter_add_instance_count')

    class Meta:
        model = CollectType
        fields = ['name', 'collector', 'add_policy_count', 'add_instance_count']

    def filter_add_policy_count(self, queryset, name, value):
        """The view adds the permission-aware count to serialized results."""
        return queryset

    def filter_add_instance_count(self, queryset, name, value):
        """The view adds the permission-aware count to serialized results."""
        return queryset


class CollectInstanceFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    collect_type = filters.CharFilter(field_name='collect_type__name', lookup_expr='icontains')

    class Meta:
        model = CollectInstance
        fields = ['name', 'collect_type']


class CollectConfigFilter(filters.FilterSet):
    collect_instance = filters.CharFilter(field_name='collect_instance__name', lookup_expr='icontains')
    file_type = filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = CollectConfig
        fields = ['collect_instance', 'file_type']
