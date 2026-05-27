import base64

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet

from apps.cmdb.serializers.config_file_serializer import ConfigFileListSerializer, ConfigFileVersionSerializer
from apps.cmdb.services.config_file_service import ConfigFileService
from apps.cmdb.models.config_file_version import ConfigFileVersion
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination


class ConfigFileVersionViewSet(GenericViewSet):
    queryset = ConfigFileVersion.objects.select_related("collect_task").all()
    serializer_class = ConfigFileVersionSerializer
    pagination_class = CustomPageNumberPagination

    def get_filtered_queryset(self, request):
        return ConfigFileService.filter_queryset_by_task_permission(request, self.get_queryset())

    @HasPermission("auto_collection-View")
    def list(self, request, *args, **kwargs):
        instance_id = (request.GET.get("instance_id") or "").strip()
        file_path = (request.GET.get("file_path") or "").strip()
        if not instance_id or not file_path:
            return WebUtils.response_error(error_message="instance_id 和 file_path 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_filtered_queryset(request).filter(instance_id=instance_id, file_path=file_path)
        status_value = (request.GET.get("status") or "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)

        page = self.paginate_queryset(queryset.order_by("-created_at"))
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return WebUtils.response_success(serializer.data)

    @HasPermission("auto_collection-View")
    @action(methods=["GET"], detail=True, url_path="content")
    def content(self, request, pk=None):
        instance = self.get_filtered_queryset(request).filter(pk=pk).first()
        if not instance:
            return WebUtils.response_error(error_message="版本不存在", status_code=status.HTTP_404_NOT_FOUND)
        if not instance.content:
            return WebUtils.response_error(error_message="当前版本没有可查看的内容", status_code=status.HTTP_400_BAD_REQUEST)
        encoding = (request.GET.get("encoding") or "utf-8").strip().lower()
        try:
            raw_content = instance.read_content_bytes()
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

    @HasPermission("auto_collection-View")
    @action(methods=["GET"], detail=False, url_path="diff")
    def diff(self, request):
        version_id_1 = request.GET.get("version_id_1")
        version_id_2 = request.GET.get("version_id_2")
        if not version_id_1 or not version_id_2:
            return WebUtils.response_error(error_message="version_id_1 和 version_id_2 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_filtered_queryset(request)
        version_1 = queryset.filter(pk=version_id_1).first()
        version_2 = queryset.filter(pk=version_id_2).first()
        if not version_1 or not version_2:
            return WebUtils.response_error(error_message="对比版本不存在", status_code=status.HTTP_404_NOT_FOUND)
        if not version_1.content or not version_2.content:
            return WebUtils.response_error(error_message="仅支持对比采集成功的版本", status_code=status.HTTP_400_BAD_REQUEST)

        content_1 = version_1.read_content()
        content_2 = version_2.read_content()
        diff_text = ConfigFileService.generate_diff(content_1, content_2, version_1.version, version_2.version)
        return WebUtils.response_success({"version_1": version_1.version, "version_2": version_2.version, "diff_text": diff_text})

    @HasPermission("auto_collection-View")
    @action(methods=["GET"], detail=False, url_path="file_list")
    def file_list(self, request):
        instance_id = (request.GET.get("instance_id") or "").strip()
        if not instance_id:
            return WebUtils.response_error(error_message="instance_id 不能为空", status_code=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_filtered_queryset(request).filter(instance_id=instance_id)
        data = ConfigFileService.get_file_list(instance_id, base_queryset=queryset)
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

    @HasPermission("auto_collection-Edit")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_filtered_queryset(request).filter(pk=kwargs.get("pk")).first()
        if not instance:
            return WebUtils.response_error(error_message="版本不存在", status_code=status.HTTP_404_NOT_FOUND)
        deleted_id = instance.id
        instance.delete()
        return WebUtils.response_success({"deleted_id": deleted_id})
