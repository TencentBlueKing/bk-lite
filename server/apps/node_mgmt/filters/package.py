from django_filters import rest_framework as filters

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class PackageVersionFilter(filters.FilterSet):
    os = filters.CharFilter(field_name="os", lookup_expr="exact", label="操作系统")
    cpu_architecture = filters.CharFilter(method="filter_cpu_architecture", label="CPU架构")
    type = filters.CharFilter(field_name="type", lookup_expr="exact", label="包类型(控制器/采集器)")
    object = filters.CharFilter(field_name="object", lookup_expr="exact", label="对象")
    version = filters.CharFilter(field_name="version", lookup_expr="icontains", label="包版本号")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains", label="节点名称")

    def filter_cpu_architecture(self, queryset, name, value):
        normalized_arch = normalize_cpu_architecture(value)
        if normalized_arch:
            return queryset.filter(cpu_architecture=normalized_arch)

        target_os = self.data.get("os")
        target_type = self.data.get("type")
        target_object = self.data.get("object")
        if target_os == NodeConstants.WINDOWS_OS and target_type == "controller" and target_object == "Controller":
            return queryset.filter(cpu_architecture=NodeConstants.X86_64_ARCH)

        return queryset

    class Meta:
        model = PackageVersion
        fields = ["os", "cpu_architecture", "name", "object", "type", "version"]
