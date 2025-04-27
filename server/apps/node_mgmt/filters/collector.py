from django_filters import rest_framework as filters
from apps.node_mgmt.models.sidecar import Collector


class CollectorFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains', label='采集器名称')
    node_operating_system = filters.CharFilter(field_name='node_operating_system', lookup_expr='exact',
                                               label='操作系统')

    class Meta:
        model = Collector
        fields = ['name', 'node_operating_system']
