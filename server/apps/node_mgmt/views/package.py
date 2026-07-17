from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.filters.package import PackageVersionFilter
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.serializers.package import PackageVersionSerializer
from apps.node_mgmt.services.package import PackageService
from config.drf.pagination import CustomPageNumberPagination


PACKAGE_WRITE_PERMISSIONS = {
    (PackageConstants.TYPE_CONTROLLER, "create"): "controller_packet-AddPacket",
    (PackageConstants.TYPE_CONTROLLER, "destroy"): "controller_packet-Delete",
    (PackageConstants.TYPE_COLLECTOR, "create"): "collector_packet-AddPacket",
    (PackageConstants.TYPE_COLLECTOR, "destroy"): "collector_packet-Delete",
}


class PackageMgmtView(
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    GenericViewSet,
):
    queryset = PackageVersion.objects.all()
    serializer_class = PackageVersionSerializer
    filterset_class = PackageVersionFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return super().get_queryset().order_by("-id")

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @staticmethod
    def _require_write_permission(request, package_type, action):
        if getattr(request.user, "is_superuser", False):
            return

        required_permission = PACKAGE_WRITE_PERMISSIONS.get((package_type, action))
        user_permissions = getattr(request.user, "permission", set()) or set()
        if isinstance(user_permissions, dict):
            user_permissions = user_permissions.get("node", set())

        if not required_permission or required_permission not in user_permissions:
            raise PermissionDenied()

    def destroy(self, request, *args, **kwargs):
        # 删除文件，成功了再删除数据
        obj = self.get_object()
        self._require_write_permission(request, obj.type, "destroy")
        PackageService.delete_file(obj)
        return super().destroy(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return WebUtils.response_error(error_message="请上传文件")

        package_type = request.data.get("type")  # collector 或 controller
        os_type = request.data.get("os")  # linux 或 windows
        cpu_architecture = request.data.get("cpu_architecture") or NodeConstants.X86_64_ARCH
        object_name = request.data.get("object")  # 采集器/控制器名称

        # 校验必填参数
        if not all([package_type, os_type, object_name]):
            return WebUtils.response_error(error_message="请填写完整的包类型、操作系统和对象名称")

        self._require_write_permission(request, package_type, "create")

        # 校验包并自动识别版本
        is_valid, error_message, parsed_info = PackageService.validate_package(
            uploaded_file.name, package_type, os_type, object_name, cpu_architecture
        )

        if not is_valid:
            return WebUtils.response_error(error_message=error_message)

        # 使用自动识别的版本号和去掉版本号的文件名
        data = dict(
            os=os_type,
            cpu_architecture=PackageService.normalize_upload_cpu_architecture(cpu_architecture),
            type=package_type,
            object=object_name,
            version=parsed_info["version"],  # 自动识别的版本号
            name=parsed_info["name_without_version"],  # 存储去掉版本号的文件名
            description=request.data.get("description", ""),
            created_by=request.user.username,
            updated_by=request.user.username,
        )

        existing_package = parsed_info.get("existing_package")
        if existing_package:
            PackageService.upload_file(uploaded_file, data)
            existing_package.description = data.get("description", existing_package.description)
            existing_package.updated_by = request.user.username
            existing_package.save(update_fields=["description", "updated_by", "updated_at"])
            return WebUtils.response_success(PackageVersionSerializer(existing_package).data)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        PackageService.upload_file(uploaded_file, data)
        self.perform_create(serializer)

        return WebUtils.response_success(serializer.data)

    @action(detail=False, methods=["get"], url_path="download/(?P<pk>.+?)")
    def download(self, request, pk=None):
        obj = PackageVersion.objects.get(pk=pk)
        file, name = PackageService.download_file(obj)
        return WebUtils.response_file(file, name)
