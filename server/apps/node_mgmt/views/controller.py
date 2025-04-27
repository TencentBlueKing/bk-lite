from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from apps.node_mgmt.filters.controller import ControllerFilter
from apps.node_mgmt.models import Controller
from apps.node_mgmt.serializers.controller import ControllerSerializer


class ControllerViewSet(mixins.ListModelMixin,
                       GenericViewSet):
    queryset = Controller.objects.all()
    serializer_class = ControllerSerializer
    filterset_class = ControllerFilter
    search_fields = ['id', 'name', 'introduction']

    @swagger_auto_schema(
        operation_summary="获取控制器列表",
        manual_parameters=[
            openapi.Parameter('os', openapi.IN_QUERY, description="操作系统", type=openapi.TYPE_STRING),
            openapi.Parameter('name', openapi.IN_QUERY, description="控制器名称", type=openapi.TYPE_STRING),
        ],
        tags=['Controller']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
