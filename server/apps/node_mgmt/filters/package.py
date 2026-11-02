from django_filters import rest_framework as filters
from django.db.models import Q

from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.utils.architecture import normalize_cpu_architecture


class PackageVersionFilter(filters.FilterSet):
    os = filters.CharFilter(field_name="os", lookup_expr="exact", label="操作系统")
    cpu_architecture = filters.CharFilter(method="filter_cpu_architecture", label="CPU架构")
    type = filters.CharFilter(field_name="type", lookup_expr="exact", label="包类型(控制器/采集器)")
    object = filters.CharFilter(field_name="object", lookup_expr="exact", label="对象")
    version = filters.CharFilter(field_name="version", lookup_expr="icontains", label="包版本号")
    name = filters.CharFilter(field_name="name", lookup_expr="icontains", label="节点名称")

    def filter_queryset(self, queryset):
        if self._collector_package_query_is_unbounded():
            return queryset.none()
        return super().filter_queryset(queryset)

    def _collector_package_query_is_unbounded(self) -> bool:
        """采集器安装/更新必须带上目标 OS 和 CPU 架构。

        管理端不带 object/type 的全量列表保持原样。控制器查询继续走原有架构规则。
        只带采集器 object、且 OS 与架构都为空的请求，是安装弹窗首次打开时的空参数形态，
        不能再返回全部操作系统和架构。
        """
        package_type = str(self.data.get("type") or "").strip()
        package_object = str(self.data.get("object") or "").strip()
        package_os = str(self.data.get("os") or "").strip()
        architecture = normalize_cpu_architecture(self.data.get("cpu_architecture"))

        if package_type == PackageConstants.TYPE_CONTROLLER or package_object == "Controller":
            return False

        if package_type == PackageConstants.TYPE_COLLECTOR:
            return not package_os or not architecture

        return bool(package_object) and not package_os and not architecture

    def filter_cpu_architecture(self, queryset, name, value):
        normalized_arch = normalize_cpu_architecture(value)
        if normalized_arch:
            target_type = self.data.get("type")
            target_object = self.data.get("object")
            if normalized_arch == NodeConstants.X86_64_ARCH and target_type == "controller" and target_object == "Controller":
                return queryset.filter(Q(cpu_architecture=normalized_arch) | Q(cpu_architecture=""))
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
