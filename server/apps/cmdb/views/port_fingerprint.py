from rest_framework import status

from apps.cmdb.filters.collect_filters import PortFingerprintFilter
from apps.cmdb.models.collect_model import PortFingerprint
from apps.cmdb.serializers.port_fingerprint_serializer import PortFingerprintSerializer
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class PortFingerprintViewSet(ModelViewSet):
    queryset = PortFingerprint.objects.all()
    serializer_class = PortFingerprintSerializer
    ordering_fields = ["updated_at", "port"]
    ordering = ["port", "target_type"]
    filterset_class = PortFingerprintFilter
    pagination_class = CustomPageNumberPagination

    @HasPermission("soid_library-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("soid_library-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("soid_library-Add")
    def create(self, request, *args, **kwargs):
        port = request.data.get("port")
        target_type = str(request.data.get("target_type") or "").strip()
        if port not in (None, "") and target_type:
            try:
                port_value = int(port)
            except (TypeError, ValueError):
                port_value = None
            if port_value is not None and PortFingerprint.objects.filter(port=port_value, target_type=target_type).exists():
                return WebUtils.response_error(error_message="该端口与类型已存在", status_code=status.HTTP_400_BAD_REQUEST)
        return super().create(request, *args, **kwargs)

    @HasPermission("soid_library-Delete")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.built_in:
            return WebUtils.response_error(error_message="不能删除内置端口指纹", status_code=status.HTTP_400_BAD_REQUEST)
        return super().destroy(request, *args, **kwargs)
