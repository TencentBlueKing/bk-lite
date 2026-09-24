from django.db import IntegrityError
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import node_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.node import NodeConstants
from apps.node_mgmt.constants.package import PackageConstants
from apps.node_mgmt.filters.package import PackageVersionFilter
from apps.node_mgmt.models.package import PackageVersion
from apps.node_mgmt.serializers.package import PackageVersionSerializer
from apps.node_mgmt.services.collector_release.constants import CollectorReleaseConstants as C
from apps.node_mgmt.services.collector_release.errors import PACK_TOO_LARGE, issue
from apps.node_mgmt.services.collector_release.service import CollectorReleaseService
from apps.node_mgmt.services.package import PackageService
from apps.node_mgmt.utils.package_permission import require_package_write_permission
from config.drf.pagination import CustomPageNumberPagination


def _build_actor_context_optional(request):
    try:
        from apps.monitor.views.node_mgmt import _build_actor_context

        return _build_actor_context(request)
    except Exception:
        logger.exception("event=collect_config_stale_count_failed failed_stage=actor_context error_type=count_error")
        return None


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
        return PackageService.ready_queryset().order_by("-id")

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @staticmethod
    def _require_write_permission(request, package_type, action):
        require_package_write_permission(request, package_type, action)

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
            try:
                result = PackageService.upload_file(uploaded_file, data, existing_package=existing_package)
            except IntegrityError:
                return WebUtils.response_error(
                    error_message=PackageConstants.ERROR_MSG_VERSION_EXISTS.format(version=data["version"])
                )
            if isinstance(result, PackageVersion):
                return WebUtils.response_success(PackageVersionSerializer(result).data)
            existing_package.description = data.get("description", existing_package.description)
            existing_package.updated_by = request.user.username
            existing_package.save(update_fields=["description", "updated_by", "updated_at"])
            return WebUtils.response_success(PackageVersionSerializer(existing_package).data)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        try:
            result = PackageService.upload_file(uploaded_file, data)
        except IntegrityError:
            return WebUtils.response_error(
                error_message=PackageConstants.ERROR_MSG_VERSION_EXISTS.format(version=data["version"])
            )
        if isinstance(result, PackageVersion):
            return WebUtils.response_success(PackageVersionSerializer(result).data)
        self.perform_create(serializer)

        return WebUtils.response_success(serializer.data)

    @action(detail=False, methods=["get"], url_path="download/(?P<pk>.+?)")
    def download(self, request, pk=None):
        obj = self.get_queryset().get(pk=pk)
        file, name = PackageService.download_file(obj)
        return WebUtils.response_file(file, name)

    @action(detail=False, methods=["post"], url_path="release/preview")
    def release_preview(self, request):
        self._require_write_permission(request, PackageConstants.TYPE_COLLECTOR, "create")
        try:
            content_length = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > C.MAX_COMPRESSED_BYTES:
            return WebUtils.response_success(
                {
                    "token": "",
                    "has_errors": True,
                    "issues": [
                        issue(
                            PACK_TOO_LARGE,
                            f"压缩包超过上限 {C.MAX_COMPRESSED_BYTES // (1024 * 1024)}MB，当前请求约 {content_length / (1024 * 1024):.1f}MB。",
                            hint="这通常是网关或上传限制，请去掉部分架构后再导入。",
                            details={"size": content_length, "limit": C.MAX_COMPRESSED_BYTES},
                        ).to_dict()
                    ],
                    "requires_confirm": [],
                    "keep_local_slots": [],
                    "pack": None,
                }
            )
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return WebUtils.response_error(error_message="请上传文件")
        result = CollectorReleaseService.preview_upload(uploaded_file)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path="release/apply")
    def release_apply(self, request):
        self._require_write_permission(request, PackageConstants.TYPE_COLLECTOR, "create")
        token = request.data.get("token")
        confirms = request.data.get("confirms") or []
        if not token:
            return WebUtils.response_error(error_message="缺少 preview token")
        try:
            result = CollectorReleaseService.apply(token, confirms, actor_context=_build_actor_context_optional(request))
        except ValidationAppException as exc:
            return WebUtils.response_error(response_data=exc.data or {}, error_message=exc.message)
        except BaseAppException as exc:
            return WebUtils.response_error(response_data=exc.data or {}, error_message=exc.message)
        return WebUtils.response_success(result)

    @action(detail=False, methods=["post"], url_path="release/discard")
    def release_discard(self, request):
        self._require_write_permission(request, PackageConstants.TYPE_COLLECTOR, "create")
        token = request.data.get("token")
        if not token:
            return WebUtils.response_error(error_message="缺少 preview token")
        return WebUtils.response_success(CollectorReleaseService.discard_staging(token))

    @action(detail=False, methods=["post"], url_path="release/restore")
    def release_restore(self, request):
        self._require_write_permission(request, PackageConstants.TYPE_COLLECTOR, "create")
        collector = request.data.get("collector")
        if not collector:
            return WebUtils.response_error(error_message="缺少 collector")
        try:
            result = CollectorReleaseService.restore_builtin(
                collector,
                actor_context=_build_actor_context_optional(request),
            )
        except BaseAppException as exc:
            return WebUtils.response_error(response_data=exc.data or {}, error_message=exc.message)
        return WebUtils.response_success(result)
