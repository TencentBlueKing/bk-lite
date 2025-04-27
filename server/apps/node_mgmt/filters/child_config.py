from django_filters import rest_framework as filters
from apps.node_mgmt.models.sidecar import ChildConfig


class ChildConfigFilter(filters.FilterSet):
    collector_config_id = filters.CharFilter(field_name='collector_config_id', lookup_expr='exact', label='采集器配置ID')

    class Meta:
        model = ChildConfig
        fields = ['collector_config_id']
