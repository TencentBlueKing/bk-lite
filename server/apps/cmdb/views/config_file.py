import base64

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.cmdb.constants.constants import OPERATE, VIEW
from apps.cmdb.models.config_file_version import ConfigFileContentStatus, ConfigFileVersion
from apps.cmdb.serializers.config_file_serializer import ConfigFileListSerializer, ConfigFileVersionSerializer
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.services.config_file_content_lifecycle import ConfigFileContentLifecycle
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.views.mixins import CmdbPermissionMixin
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination


class ConfigFileVersionViewSet(CmdbPermissionMixin, GenericViewSet):
    queryset = ConfigFileVersion.objects.select_related("collect_task").all()
    serializer_class = ConfigFileVersionSerializer
    pagination_class = CustomPageNumberPagination

    def _get_instance_or_error(self, instance_id):
        """解析 instance_id 并查询实例，返回 (instance_dict, error_response)。"""
        if not instance_id:
            return None, WebUtils.response_error(error_message="instance_id 不能为空", status_code=status.HTTP_400_BAD_REQUEST)
        try:
            instance = InstanceManage.query_entity_by_id(int(instance_id))
        except (ValueError, TypeError):
            return None, WebUtils.response_error(error_message="instance_id 格式错误", status_code=status.HTTP_400_BAD_REQUEST)
        if not instance:
            return None, WebUtils.response_error(error_message="实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        return instance, None

    def list(self, request, *args, **kwargs):
        instance_id = (request.GET.get("instance_id") or "").strip()
        file_path = (request.GET.get("file_path") or "").strip()
        if not instance_id or not file_path:
            return WebUtils.response_error(error_message="instance_id 和 file_path 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        instance, error = self._get_instance_or_error(instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        queryset = self.get_queryset().filter(instance_id=instance_id, file_path=file_path)
        status_value = (request.GET.get("status") or "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        page = self.paginate_queryset(queryset.order_by("-created_at"))
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(serializer.data)

    @action(methods=["GET"], detail=True, url_path="content")
    def content(self, request, pk=None):
        version_obj = self.get_queryset().filter(pk=pk).first()
        if not version_obj:
            return WebUtils.response_error(error_message="版本不存在", status_code=status.HTTP_404_NOT_FOUND)

        instance, error = self._get_instance_or_error(version_obj.instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        if version_obj.content_status != ConfigFileContentStatus.READY or not version_obj.content:
            return WebUtils.response_error(error_message="当前版本没有可查看的内容", status_code=status.HTTP_400_BAD_REQUEST)
        encoding = (request.GET.get("encoding") or "utf-8").strip().lower()
        try:
            raw_content = version_obj.read_content_bytes()
        except Exception as err:
            return WebUtils.response_error(
                error_message=f"读取配置文件内容失败: {err}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        try:
            content = raw_content.decode(encoding, errors="replace")
        except LookupError:
            return WebUtils.response_error(error_message=f"不支持的编码: {encoding}", status_code=status.HTTP_400_BAD_REQUEST)
        return WebUtils.response_success(
            {
                "content": content,
                "encoding": encoding,
                "raw_base64": base64.b64encode(raw_content).decode("ascii"),
            }
        )

    @action(methods=["GET"], detail=False, url_path="diff")
    def diff(self, request):
        version_id_1 = request.GET.get("version_id_1")
        version_id_2 = request.GET.get("version_id_2")
        if not version_id_1 or not version_id_2:
            return WebUtils.response_error(error_message="version_id_1 和 version_id_2 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        version_1 = self.get_queryset().filter(pk=version_id_1).first()
        version_2 = self.get_queryset().filter(pk=version_id_2).first()
        if not version_1 or not version_2:
            return WebUtils.response_error(error_message="对比版本不存在", status_code=status.HTTP_404_NOT_FOUND)

        instance_1, error = self._get_instance_or_error(version_1.instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance_1, operator=VIEW)
        if permission_error:
            return permission_error

        instance_2, error = self._get_instance_or_error(version_2.instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance_2, operator=VIEW)
        if permission_error:
            return permission_error

        if version_1.instance_id != version_2.instance_id:
            return WebUtils.response_error(error_message="仅支持对比同一实例的配置文件版本", status_code=status.HTTP_400_BAD_REQUEST)
        if version_1.file_path != version_2.file_path:
            return WebUtils.response_error(error_message="仅支持对比同一配置文件的版本", status_code=status.HTTP_400_BAD_REQUEST)

        if (
            version_1.content_status != ConfigFileContentStatus.READY
            or version_2.content_status != ConfigFileContentStatus.READY
            or not version_1.content
            or not version_2.content
        ):
            return WebUtils.response_error(error_message="仅支持对比采集成功的版本", status_code=status.HTTP_400_BAD_REQUEST)

        content_1 = version_1.read_content()
        content_2 = version_2.read_content()
        diff_text = ConfigFileService.generate_diff(content_1, content_2, version_1.version, version_2.version)
        return WebUtils.response_success({"version_1": version_1.version, "version_2": version_2.version, "diff_text": diff_text})

    @action(methods=["GET"], detail=False, url_path="file_list")
    def file_list(self, request):
        instance_id = (request.GET.get("instance_id") or "").strip()
        if not instance_id:
            return WebUtils.response_error(error_message="instance_id 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        instance, error = self._get_instance_or_error(instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance, operator=VIEW)
        if permission_error:
            return permission_error

        data = ConfigFileService.get_file_list(instance_id)
        serializer = ConfigFileListSerializer(data, many=True)
        return WebUtils.response_success(serializer.data)

    @HasPermission("auto_collection-Edit")
    @action(methods=["POST"], detail=False, url_path="receive_result")
    def receive_result(self, request):
        if not isinstance(request.data, dict):
            return WebUtils.response_error(error_message="请求体必须为 JSON 对象", status_code=status.HTTP_400_BAD_REQUEST)

        result = ConfigFileService.process_collect_result(dict(request.data))
        version_obj = result.get("version_obj")
        return WebUtils.response_success(
            {
                "version_id": version_obj.id if version_obj else None,
                "changed": bool(result.get("changed", False)),
                "task_updated": bool(result.get("task_updated", False)),
            }
        )

    @action(methods=["POST"], detail=False, url_path="create_manual")
    def create_manual(self, request):
        instance_id = (request.data.get("instance_id") or "").strip()
        model_id = (request.data.get("model_id") or "").strip()
        file_path = (request.data.get("file_path") or "").strip()
        content = request.data.get("content") or ""

        if not instance_id or not model_id or not file_path:
            return WebUtils.response_error(
                error_message="instance_id、model_id 和 file_path 不能为空",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if not content:
            return WebUtils.response_error(error_message="文件内容不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        instance, error = self._get_instance_or_error(instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance, operator=OPERATE)
        if permission_error:
            return permission_error

        try:
            result = ConfigFileService.create_manual_version(
                instance_id=instance_id,
                model_id=model_id,
                file_path=file_path,
                content=content,
            )
        except Exception as e:
            return WebUtils.response_error(
                error_message=f"创建失败: {e}",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if result.get("unchanged"):
            return WebUtils.response_error(
                error_message="该文件内容与最新版本相同，无需重复上传",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        version_obj = result["version_obj"]
        return WebUtils.response_success(
            {
                "id": version_obj.id,
                "version": version_obj.version,
                "file_name": version_obj.file_name,
                "file_path": version_obj.file_path,
            }
        )

    def destroy(self, request, *args, **kwargs):
        version_obj = self.get_queryset().filter(pk=kwargs.get("pk")).first()
        if not version_obj:
            return WebUtils.response_error(error_message="版本不存在", status_code=status.HTTP_404_NOT_FOUND)

        instance, error = self._get_instance_or_error(version_obj.instance_id)
        if error:
            return error
        permission_error = self.require_instance_permission(request, instance, operator=OPERATE)
        if permission_error:
            return permission_error

        deleted_id = version_obj.id
        ConfigFileContentLifecycle.request_delete(deleted_id)
        return WebUtils.response_success({"deleted_id": deleted_id, "content_status": ConfigFileContentStatus.DELETE_PENDING})
