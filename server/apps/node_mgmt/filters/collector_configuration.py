from django_filters import rest_framework as filters
from apps.node_mgmt.models.sidecar import CollectorConfiguration


class CollectorConfigurationFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains', label='配置名称')
    cloud_region_id = filters.NumberFilter(field_name='cloud_region_id', lookup_expr='exact', label='云区域ID')

    class Meta:
        model = CollectorConfiguration
        fields = ['name', 'cloud_region_id']
