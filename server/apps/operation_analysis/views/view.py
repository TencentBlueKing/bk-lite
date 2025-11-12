# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/7/14 17:22
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.filters.filters import DashboardModelFilter, DirectoryModelFilter, \
    TopologyModelFilter, ArchitectureModelFilter
from apps.operation_analysis.serializers.directory_serializers import DashboardModelSerializer, \
    DirectoryModelSerializer, TopologyModelSerializer, ArchitectureModelSerializer
from apps.operation_analysis.services.directory_service import DictDirectoryService
from config.drf.pagination import CustomPageNumberPagination
from apps.operation_analysis.models.models import Dashboard, Directory, Topology, Architecture


class DirectoryModelViewSet(AuthViewSet):
    """
    目录
    """
    queryset = Directory.objects.all()
    serializer_class = DirectoryModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DirectoryModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory"
    ORGANIZATION_FIELD = "groups"

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super(DirectoryModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DirectoryModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("view-AddCatalogue")
    def create(self, request, *args, **kwargs):
        data = request.data
        Directory.objects.create(**data)
        return Response(data)

    @HasPermission("view-EditCatalogue")
    def update(self, request, *args, **kwargs):
        Directory.objects.filter(id=kwargs["pk"]).update(**request.data)
        return Response(request.data)

    @HasPermission("view-DeleteCatalogue")
    def destroy(self, request, *args, **kwargs):
        return super(DirectoryModelViewSet, self).destroy(request, *args, **kwargs)

    # @HasPermission("view-View")
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        result = DictDirectoryService.get_dict_trees(request)
        return Response(result)


class DashboardModelViewSet(AuthViewSet):
    """
    仪表盘
    """
    queryset = Dashboard.objects.all()
    serializer_class = DashboardModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DashboardModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory.dashboard"
    ORGANIZATION_FIELD = "groups"  # 使用 groups 字段作为组织字段

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super(DashboardModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super(DashboardModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        return super(DashboardModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        return super(DashboardModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        return super(DashboardModelViewSet, self).destroy(request, *args, **kwargs)


class TopologyModelViewSet(AuthViewSet):
    """
    拓扑图
    """
    queryset = Topology.objects.all()
    serializer_class = TopologyModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = TopologyModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory.topology"
    ORGANIZATION_FIELD = "groups"  # 使用 groups 字段作为组织字段

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super(TopologyModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super(TopologyModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        return super(TopologyModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        return super(TopologyModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        return super(TopologyModelViewSet, self).destroy(request, *args, **kwargs)


class ArchitectureModelViewSet(AuthViewSet):
    """
    架构图
    """
    queryset = Architecture.objects.all()
    serializer_class = ArchitectureModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = ArchitectureModelFilter
    pagination_class = CustomPageNumberPagination
    permission_key = "directory.architecture"
    ORGANIZATION_FIELD = "groups"  # 使用 groups 字段作为组织字段

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super(ArchitectureModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super(ArchitectureModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        return super(ArchitectureModelViewSet, self).create(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        return super(ArchitectureModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        return super(ArchitectureModelViewSet, self).destroy(request, *args, **kwargs)
