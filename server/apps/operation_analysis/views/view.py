# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/7/14 17:22
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.filters.filters import ArchitectureModelFilter, DashboardModelFilter, DirectoryModelFilter, TopologyModelFilter
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Topology
from apps.operation_analysis.serializers.directory_serializers import (
    ArchitectureModelSerializer,
    DashboardModelSerializer,
    DirectoryModelSerializer,
    TopologyModelSerializer,
)
from apps.operation_analysis.services.directory_service import DictDirectoryService
from config.drf.pagination import CustomPageNumberPagination


def _raise_if_builtin(instance, action_name="修改"):
    """如果对象是内置对象，拒绝操作"""
    if getattr(instance, "is_build_in", False):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied(f"内置对象不允许{action_name}")


class BuiltinVisibleMixin:
    """
    内置对象跳过实例级权限过滤（但仍受组织过滤约束）。
    通过 get_queryset_by_permission 将内置对象从权限过滤中排除后合并；
    在 retrieve 中内置对象跳过实例级校验。
    """

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        builtin_qs = queryset.filter(is_build_in=True)
        normal_qs = queryset.filter(is_build_in=False)
        # 内置对象：复用 filter_by_group 做组织过滤（支持 include_children），跳过实例级权限
        _ct, _ic, _of, org_query = self.filter_by_group(builtin_qs, request, request.user)
        builtin_filtered = builtin_qs.filter(org_query)
        # 普通对象：走完整权限过滤
        normal_filtered = super().get_queryset_by_permission(request, normal_qs, permission_key)
        return (normal_filtered | builtin_filtered).distinct()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if getattr(instance, "is_build_in", False):
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
        return super().retrieve(request, *args, **kwargs)


class DirectoryModelViewSet(BuiltinVisibleMixin, AuthViewSet):
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
        data = {k: v for k, v in request.data.items() if k not in ("is_build_in", "build_in_key")}
        Directory.objects.create(**data)
        return Response(data)

    @HasPermission("view-EditCatalogue")
    def update(self, request, *args, **kwargs):
        instance = Directory.objects.filter(id=kwargs["pk"]).first()
        if instance:
            _raise_if_builtin(instance, "编辑")
        data = {k: v for k, v in request.data.items() if k not in ("is_build_in", "build_in_key")}
        Directory.objects.filter(id=kwargs["pk"]).update(**data)
        return Response(data)

    @HasPermission("view-EditCatalogue")
    def partial_update(self, request, *args, **kwargs):
        instance = Directory.objects.filter(id=kwargs["pk"]).first()
        if instance:
            _raise_if_builtin(instance, "编辑")
        data = {k: v for k, v in request.data.items() if k not in ("is_build_in", "build_in_key")}
        Directory.objects.filter(id=kwargs["pk"]).update(**data)
        return Response(data)

    @HasPermission("view-DeleteCatalogue")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        return super(DirectoryModelViewSet, self).destroy(request, *args, **kwargs)

    @HasPermission("view-View")
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        result = DictDirectoryService.get_dict_trees(request)
        return Response(result)


class DashboardModelViewSet(BuiltinVisibleMixin, AuthViewSet):
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
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(DashboardModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(DashboardModelViewSet, self).partial_update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        return super(DashboardModelViewSet, self).destroy(request, *args, **kwargs)


class TopologyModelViewSet(BuiltinVisibleMixin, AuthViewSet):
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
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(TopologyModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(TopologyModelViewSet, self).partial_update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        return super(TopologyModelViewSet, self).destroy(request, *args, **kwargs)


class ArchitectureModelViewSet(BuiltinVisibleMixin, AuthViewSet):
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
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(ArchitectureModelViewSet, self).update(request, *args, **kwargs)

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        return super(ArchitectureModelViewSet, self).partial_update(request, *args, **kwargs)

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        return super(ArchitectureModelViewSet, self).destroy(request, *args, **kwargs)
