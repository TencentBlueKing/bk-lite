from django_filters import rest_framework as filters

from apps.node_mgmt.models.package import PackageVersion


class PackageVersionFilter(filters.FilterSet):
    os = filters.CharFilter(field_name='os', lookup_expr='exact', label='操作系统')
    type = filters.CharFilter(field_name='type', lookup_expr='exact', label='包类型(控制器/采集器)')
    object = filters.CharFilter(field_name='object', lookup_expr='exact', label='对象')
    version = filters.CharFilter(field_name='version', lookup_expr='icontains', label='包版本号')
    name = filters.CharFilter(field_name='name', lookup_expr='icontains', label='节点名称')

    class Meta:
        model = PackageVersion
        fields = ['os', 'name', 'object', 'type', 'version']
