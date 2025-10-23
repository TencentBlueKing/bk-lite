from django_filters import rest_framework as filters
from django.db.models import Count

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
        """
        过滤器方法，用于处理add_policy_count参数
        使用annotate进行聚合查询，避免N+1问题
        """
        if value:
            # 使用annotate一次性计算所有采集类型的策略数量
            return queryset.annotate(policy_count=Count('policy'))
        return queryset

    def filter_add_instance_count(self, queryset, name, value):
        """
        过滤器方法，用于处理add_instance_count参数
        使用annotate进行聚合查询，避免N+1问题
        """
        if value:
            # 使用annotate一次性计算所有采集类型的实例数量
            return queryset.annotate(instance_count=Count('collectinstance'))
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