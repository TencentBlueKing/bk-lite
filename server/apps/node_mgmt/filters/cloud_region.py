from django_filters import rest_framework as filters
from apps.node_mgmt.models.cloud_region import CloudRegion


class CloudRegionFilter(filters.FilterSet):
    name = filters.CharFilter(field_name='name', lookup_expr='icontains', label='云区域名称')
    introduction = filters.CharFilter(field_name='introduction', lookup_expr='icontains', label='云区域介绍')

    class Meta:
        model = CloudRegion
        fields = ['name', 'introduction']
