from rest_framework import status

from apps.cmdb.filters.collect_filters import ProcessFingerprintFilter
from apps.cmdb.models.collect_model import ProcessFingerprint
from apps.cmdb.serializers.process_fingerprint_serializer import ProcessFingerprintSerializer
from apps.cmdb.services.process_fingerprint import FINGERPRINT_TARGET_TYPES
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class ProcessFingerprintViewSet(ModelViewSet):
    queryset = ProcessFingerprint.objects.all()
    serializer_class = ProcessFingerprintSerializer
    ordering_fields = ["updated_at", "target_type"]
    ordering = ["target_type", "id"]
    filterset_class = ProcessFingerprintFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("soid_library-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("soid_library-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("soid_library-Add")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.built_in:
            allowed = set(request.data.keys()) - {"enabled"}
            if allowed:
                return WebUtils.response_error(error_message="内置进程指纹只能停用或启用", status_code=status.HTTP_400_BAD_REQUEST)
        return super().partial_update(request, *args, **kwargs)

    @HasPermission("soid_library-Add")
    def create(self, request, *args, **kwargs):
        target_type = str(request.data.get("target_type") or "").strip()
        linux_process = str(request.data.get("linux_process") or "").strip()
        windows_image = str(request.data.get("windows_image") or "").strip()
        if target_type and target_type not in FINGERPRINT_TARGET_TYPES:
            return WebUtils.response_error(error_message="该类型不支持网段进程指纹", status_code=status.HTTP_400_BAD_REQUEST)
        if (
            target_type
            and ProcessFingerprint.objects.filter(
                target_type=target_type,
                linux_process=linux_process,
                windows_image=windows_image,
            ).exists()
        ):
            return WebUtils.response_error(error_message="该进程指纹已存在", status_code=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)

    @HasPermission("soid_library-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.built_in:
            return WebUtils.response_error(error_message="不能删除内置进程指纹", status_code=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)
