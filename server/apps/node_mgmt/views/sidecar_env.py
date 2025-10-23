from rest_framework.decorators import action
from rest_framework import viewsets, mixins
from rest_framework.viewsets import GenericViewSet

from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.filters.sidecar_env import SidecarEnvFilter
from apps.node_mgmt.models.cloud_region import SidecarEnv
from apps.node_mgmt.serializers.sidecar_env import SidecarEnvSerializer, EnvVariableCreateSerializer, \
    EnvVariableUpdateSerializer, BulkDeleteEnvVariableSerializer


class SidecarEnvViewSet(mixins.CreateModelMixin,
                        mixins.UpdateModelMixin,
                        mixins.DestroyModelMixin,
                        mixins.ListModelMixin,
                        GenericViewSet):
    queryset = SidecarEnv.objects.all()
    serializer_class = SidecarEnvSerializer
    filterset_class = SidecarEnvFilter
    search_fields = ['key', 'description']

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.serializer_class = EnvVariableCreateSerializer
        return super().create(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='bulk_delete')
    def bulk_delete(self, request):
        serializer = BulkDeleteEnvVariableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['ids']
        deleted_count, _ = SidecarEnv.objects.filter(id__in=ids).delete()
        return WebUtils.response_success({'success': True, 'message': f'成功删除数量: {deleted_count}'})
