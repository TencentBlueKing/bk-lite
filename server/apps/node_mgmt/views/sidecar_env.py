from rest_framework.decorators import action
from rest_framework import viewsets, mixins
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
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

    @swagger_auto_schema(
        operation_summary="获取环境变量列表",
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, description="模糊搜索(key, description)",
                              type=openapi.TYPE_STRING),
            openapi.Parameter('cloud_region_id', openapi.IN_QUERY, description="云区域ID", type=openapi.TYPE_INTEGER,
                              required=True),
        ],
        tags=['SidecarEnv Variable']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="创建环境变量",
        tags=['SidecarEnv Variable'],
        request_body=EnvVariableCreateSerializer
    )
    def create(self, request, *args, **kwargs):
        self.serializer_class = EnvVariableCreateSerializer
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="部分更新环境变量",
        tags=['SidecarEnv Variable'],
        request_body=EnvVariableUpdateSerializer
    )
    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = EnvVariableUpdateSerializer
        return super().partial_update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="删除环境变量",
        tags=['SidecarEnv Variable']
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @swagger_auto_schema(
        method='post',
        operation_summary="批量删除环境变量",
        request_body=BulkDeleteEnvVariableSerializer,
        tags=['SidecarEnv Variable']
    )
    @action(detail=False, methods=['post'], url_path='bulk_delete')
    def bulk_delete(self, request):
        serializer = BulkDeleteEnvVariableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = serializer.validated_data['ids']
        deleted_count, _ = SidecarEnv.objects.filter(id__in=ids).delete()
        return WebUtils.response_success({'success': True, 'message': f'成功删除数量: {deleted_count}'})
