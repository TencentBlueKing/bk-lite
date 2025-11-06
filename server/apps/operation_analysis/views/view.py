# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/7/14 17:22
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.operation_analysis.filters.filters import DashboardModelFilter, DirectoryModelFilter, \
    TopologyModelFilter, ArchitectureModelFilter
from apps.operation_analysis.serializers.directory_serializers import DashboardModelSerializer, \
    DirectoryModelSerializer, TopologyModelSerializer, ArchitectureModelSerializer
from apps.operation_analysis.services.directory_service import DictDirectoryService
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet
from apps.operation_analysis.models.models import Dashboard, Directory, Topology, Architecture


class DirectoryModelViewSet(ModelViewSet):
    """
    目录
    """
    queryset = Directory.objects.all()
    serializer_class = DirectoryModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DirectoryModelFilter
    pagination_class = CustomPageNumberPagination

    def create(self, request, *args, **kwargs):
        data = request.data
        Directory.objects.create(**data)
        return Response(data)

    def update(self, request, *args, **kwargs):
        Directory.objects.filter(id=kwargs["pk"]).update(**request.data)
        return Response(request.data)

    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        result = DictDirectoryService.get_dict_trees(request)
        return Response(result)


class DashboardModelViewSet(ModelViewSet):
    """
    仪表盘
    """
    queryset = Dashboard.objects.all()
    serializer_class = DashboardModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = DashboardModelFilter
    pagination_class = CustomPageNumberPagination


class TopologyModelViewSet(ModelViewSet):
    """
    拓扑图
    """
    queryset = Topology.objects.all()
    serializer_class = TopologyModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = TopologyModelFilter
    pagination_class = CustomPageNumberPagination


class ArchitectureModelViewSet(ModelViewSet):
    """
    架构图
    """
    queryset = Architecture.objects.all()
    serializer_class = ArchitectureModelSerializer
    ordering_fields = ["id"]
    ordering = ["id"]
    filterset_class = ArchitectureModelFilter
    pagination_class = CustomPageNumberPagination
