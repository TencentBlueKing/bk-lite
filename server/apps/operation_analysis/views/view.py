# -- coding: utf-8 --
# @File: view.py
# @Time: 2025/7/14 17:22
# @Author: windyzhao
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.operation_analysis.common.audit_log import get_response_name, log_ops_analysis_success
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


def _partial_update_with_auth(viewset, request, *args, **kwargs):
    """在 ops-analysis 本地保留 PATCH 语义，避免修改公共 AuthViewSet。"""
    user = getattr(request, "user", None)
    data = request.data
    instance = viewset.get_object()
    org_field = viewset.ORGANIZATION_FIELD
    instance_org_value = getattr(instance, org_field, [])
    if not isinstance(instance_org_value, list):
        instance_org_value = []

    if getattr(user, "is_superuser", False):
        if org_field in data:
            org_values = viewset._normalize_org_values(data, org_field)
            delete_team = [i for i in instance_org_value if i not in org_values]
            viewset.delete_rules(instance.id, delete_team)

        serializer = viewset.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        viewset.perform_update(serializer)

        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    return AuthViewSet.update(viewset, request, *args, partial=True, **kwargs)


def _build_validation_error_response(error):
    detail = getattr(error, "detail", None)
    if not isinstance(detail, dict) or "detail" not in detail or "data" not in detail:
        raise error

    message = detail.get("detail")
    if isinstance(message, list):
        message = message[0] if message else "请求失败"

    return Response({"detail": str(message), "data": detail.get("data")}, status=400)


def _execute_with_clean_validation_error(handler):
    try:
        return handler()
    except ValidationError as error:
        return _build_validation_error_response(error)


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
        response = super(DirectoryModelViewSet, self).create(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增目录: {name}")
        return response

    @HasPermission("view-EditCatalogue")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = super(DirectoryModelViewSet, self).update(request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑目录: {name}")
        return response

    @HasPermission("view-EditCatalogue")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _partial_update_with_auth(self, request, *args, **kwargs)
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑目录: {name}")
        return response

    @HasPermission("view-DeleteCatalogue")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super(DirectoryModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除目录: {name}")
        return response

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
        response = _execute_with_clean_validation_error(lambda: super(DashboardModelViewSet, self).create(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增仪表盘: {name}")
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: super(DashboardModelViewSet, self).update(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑仪表盘: {name}")
        return response

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑仪表盘: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super(DashboardModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除仪表盘: {name}")
        return response


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
        response = _execute_with_clean_validation_error(lambda: super(TopologyModelViewSet, self).create(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增拓扑图: {name}")
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: super(TopologyModelViewSet, self).update(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑拓扑图: {name}")
        return response

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑拓扑图: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super(TopologyModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除拓扑图: {name}")
        return response


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
        response = _execute_with_clean_validation_error(lambda: super(ArchitectureModelViewSet, self).create(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增架构图: {name}")
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: super(ArchitectureModelViewSet, self).update(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑架构图: {name}")
        return response

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑架构图: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super(ArchitectureModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除架构图: {name}")
        return response
