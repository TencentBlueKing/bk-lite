from django_filters import rest_framework as filters
from apps.node_mgmt.models.cloud_region import SidecarEnv


class SidecarEnvFilter(filters.FilterSet):
    key = filters.CharFilter(field_name='key', lookup_expr='exact', label='变量名')
    cloud_region_id = filters.NumberFilter(field_name='cloud_region_id', lookup_expr='exact', label='云区域ID')

    class Meta:
        model = SidecarEnv
        fields = ['key', 'cloud_region_id']
