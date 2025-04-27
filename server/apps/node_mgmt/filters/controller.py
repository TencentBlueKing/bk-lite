from django_filters import rest_framework as filters

from apps.node_mgmt.models import Controller


class ControllerFilter(filters.FilterSet):
    os = filters.CharFilter(field_name='os', lookup_expr='exact', label='操作系统')
    name = filters.CharFilter(field_name='name', lookup_expr='exact', label='控制器名称')

    class Meta:
        model = Controller
        fields = ['name', 'os']
