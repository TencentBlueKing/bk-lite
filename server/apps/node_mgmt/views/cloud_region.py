from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response
from rest_framework import status

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.loader import LanguageLoader
from apps.core.utils.web_utils import WebUtils
from apps.node_mgmt.constants.language import LanguageConstants
from apps.node_mgmt.constants.cloudregion_service import CloudRegionServiceConstants
from apps.node_mgmt.filters.cloud_region import CloudRegionFilter
from apps.node_mgmt.models import Node
from apps.node_mgmt.serializers.cloud_region import CloudRegionSerializer, CloudRegionUpdateSerializer
from apps.node_mgmt.models.cloud_region import CloudRegion, CloudRegionService
from apps.node_mgmt.tasks.cloud_server_deployed import deployed_cloud_services


class CloudRegionViewSet(mixins.ListModelMixin,
                         mixins.UpdateModelMixin,
                         mixins.DestroyModelMixin,
                         mixins.CreateModelMixin,
                         GenericViewSet):
    queryset = CloudRegion.objects.all()
    serializer_class = CloudRegionSerializer
    filterset_class = CloudRegionFilter
    search_fields = ['name', 'introduction']  # 搜索字段

    def get_queryset(self):
        """优化查询，预加载服务数据"""
        queryset = super().get_queryset()
        if self.action == 'list':
            queryset = queryset.prefetch_related('cloudregionservice_set')
        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        results = serializer.data

        lan = LanguageLoader(app=LanguageConstants.APP, default_lang=request.user.locale)

        for result in results:
            name_key = f"{LanguageConstants.CLOUD_REGION}.{result['name']}.name"
            desc_key = f"{LanguageConstants.CLOUD_REGION}.{result['name']}.description"
            result["display_name"] = lan.get(name_key) or result["name"]
            result["display_introduction"] = lan.get(desc_key) or result["introduction"]

        page = self.paginate_queryset(results)
        if page is not None:
            return self.get_paginated_response(page)

        return Response(results)

    def partial_update(self, request, *args, **kwargs):
        self.serializer_class = CloudRegionUpdateSerializer
        # 默认云区域default禁止编辑
        cloud_region_id = kwargs.get('pk')
        cloud_region = CloudRegion.objects.filter(id=cloud_region_id).first()
        if cloud_region and cloud_region.name == 'default':
            raise BaseAppException("默认云区域禁止编辑")
        return super().partial_update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        self.serializer_class = CloudRegionSerializer
        response = super().create(request, *args, **kwargs)

        # 创建成功后，初始化云区域下的服务
        if response.status_code == status.HTTP_201_CREATED:
            cloud_region_id = response.data.get('id')
            for service_name in CloudRegionServiceConstants.SERVICES:
                CloudRegionService.objects.get_or_create(
                    cloud_region_id=cloud_region_id,
                    name=service_name,
                    defaults={
                        "status": CloudRegionServiceConstants.NOT_DEPLOYED,
                        "description": f"{service_name} 服务"
                    }
                )

        return response

    def destroy(self, request, *args, **kwargs):
        # 校验云区域下是否存在节点
        cloud_region_id = kwargs.get('pk')
        if Node.objects.filter(cloud_region_id=cloud_region_id).exists():
            raise BaseAppException("该云区域下存在节点，无法删除")
        return super().destroy(request, *args, **kwargs)

    @action(methods=["post"], detail=True, url_path="deploy_services")
    def deploy_services(self, request, *args, **kwargs):
        """部署云区域服务的接口，具体实现省略"""
        deployed_cloud_services.delay(request.data)
        return WebUtils.response_success()
