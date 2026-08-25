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
from apps.operation_analysis.common.visibility_update import partial_update_groups_with_auth
from apps.operation_analysis.filters.filters import (
    ArchitectureModelFilter,
    DashboardModelFilter,
    DirectoryModelFilter,
    ReportModelFilter,
    ScreenModelFilter,
    TopologyModelFilter,
)
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, Report, Screen, Topology
from apps.operation_analysis.serializers.directory_serializers import (
    ArchitectureModelSerializer,
    DashboardModelSerializer,
    DirectoryModelSerializer,
    ReportModelSerializer,
    ScreenModelSerializer,
    TopologyModelSerializer,
)
from apps.operation_analysis.services.directory_service import DictDirectoryService
from apps.operation_analysis.services.share_service import SharePermissionDenied, create_or_get_share
from config.drf.pagination import CustomPageNumberPagination


def _raise_if_builtin(instance, action_name="修改"):
    """如果对象是内置对象，拒绝操作"""
    if getattr(instance, "is_build_in", False):
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied(f"内置对象不允许{action_name}")


def _raise_if_builtin_content_update(instance, request):
    """内置对象仅开放组织可见性配置，内容字段仍保持只读。"""
    if getattr(instance, "is_build_in", False) and set(request.data.keys()) != {"groups"}:
        _raise_if_builtin(instance, "编辑")


def _destroy_subscribable_canvas(viewset, request, *, resource_type: str, log_action: str):
    """删除画布前终止关联订阅（Dashboard / Screen / Report 共用）。"""
    from django.db import transaction

    from apps.operation_analysis.services.canvas_report.registry import get_canvas_report_adapter

    instance = viewset.get_object()
    _raise_if_builtin(instance, "删除")
    name = instance.name
    with transaction.atomic():
        adapter = get_canvas_report_adapter(resource_type)
        adapter.terminate_subscriptions_on_delete(
            instance,
            actor=getattr(request.user, "username", "") or "",
            actor_domain=getattr(request.user, "domain", "") or "",
        )
        viewset.perform_destroy(instance)
    response = Response(status=204)
    log_ops_analysis_success(request, response, "delete", log_action.format(name=name))
    return response


def _create_canvas_share_response(viewset, request, *, resource_type, resource_label):
    from rest_framework.exceptions import PermissionDenied

    from apps.operation_analysis.services.share_audit import log_share_access

    space_id = viewset._parse_current_team_cookie(request)
    resource = viewset.get_object()
    try:
        result = create_or_get_share(
            resource_type=resource_type,
            resource=resource,
            sharer=request.user,
            tenant_domain=resource.domain,
            space_id=space_id,
        )
    except SharePermissionDenied as exc:
        log_share_access(
            request,
            action="create",
            dashboard=resource if resource_type == "dashboard" else None,
            visitor=request.user,
            result="reject",
            reason="permission_denied",
        )
        raise PermissionDenied(f"无权分享该{resource_label}") from exc
    response = Response(
        {
            "id": result.link.id,
            "url": f"/ops-analysis/share/{result.token}",
            "status": result.link.status,
            "sharer_username": result.link.sharer_username,
            "resource_type": result.link.resource_type,
        }
    )
    log_share_access(
        request,
        action="create",
        link=result.link,
        dashboard=resource if resource_type == "dashboard" else None,
        visitor=request.user,
        result="ok",
    )
    return response


def _partial_update_with_auth(viewset, request, *args, **kwargs):
    """在 ops-analysis 本地保留 PATCH 语义，避免修改公共 AuthViewSet。"""
    instance = viewset.get_object()
    if getattr(instance, "is_build_in", False):
        return partial_update_groups_with_auth(viewset, request, instance)

    user = getattr(request, "user", None)
    data = request.data
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
    运营分析目录/画布：可见性仅按组织归属过滤。

    功能动作（查看/编辑/删除）仍由 HasPermission 功能权限控制；
    不依赖系统管理实例数据权限或 created_by。
    内置对象 retrieve 仍可直接返回序列化结果。
    """

    def get_queryset_by_permission(self, request, queryset, permission_key=None):
        _ct, _ic, _of, org_query = self.filter_by_group(queryset, request, request.user)
        return queryset.filter(org_query)

    def get_has_permission(self, user, instance, current_team, is_list=False, is_check=False, include_children=False):
        from apps.core.utils.user_group import normalize_user_group_ids

        user_groups = normalize_user_group_ids(getattr(user, "group_list", []))
        if include_children:
            group_tree = getattr(user, "group_tree", [])
            child_groups = self.extract_child_group_ids(group_tree, current_team)
            if child_groups:
                user_groups = child_groups

        org_field = getattr(self, "ORGANIZATION_FIELD", "groups")
        if is_list:
            for item in instance:
                org_value = getattr(item, org_field, []) or []
                if not set(org_value).intersection(set(user_groups)):
                    return False
            return True

        org_value = getattr(instance, org_field, []) or []
        return bool(set(org_value).intersection(set(user_groups)))

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
        _raise_if_builtin_content_update(instance, request)
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
        _raise_if_builtin_content_update(instance, request)
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑仪表盘: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        from apps.operation_analysis.services.canvas_report.types import RESOURCE_TYPE_DASHBOARD

        return _destroy_subscribable_canvas(
            self,
            request,
            resource_type=RESOURCE_TYPE_DASHBOARD,
            log_action="删除仪表盘: {name}",
        )

    @HasPermission("view-View")
    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, *args, **kwargs):
        return _create_canvas_share_response(
            self,
            request,
            resource_type="dashboard",
            resource_label="仪表盘",
        )


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
        _raise_if_builtin_content_update(instance, request)
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

    @HasPermission("view-View")
    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, *args, **kwargs):
        return _create_canvas_share_response(
            self,
            request,
            resource_type="topology",
            resource_label="拓扑图",
        )


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
        _raise_if_builtin_content_update(instance, request)
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

    @HasPermission("view-View")
    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, *args, **kwargs):
        return _create_canvas_share_response(
            self,
            request,
            resource_type="architecture",
            resource_label="架构图",
        )


class CanvasModelViewSet(BuiltinVisibleMixin, AuthViewSet):
    """
    新增画布类型的轻量共享 ViewSet。
    现有 Dashboard/Topology/Architecture 保持原样，避免本次变更扩大行为面。
    """

    ordering_fields = ["id"]
    ordering = ["id"]
    pagination_class = CustomPageNumberPagination
    ORGANIZATION_FIELD = "groups"
    canvas_label = "画布"

    @HasPermission("view-View")
    def retrieve(self, request, *args, **kwargs):
        return super(CanvasModelViewSet, self).retrieve(request, *args, **kwargs)

    @HasPermission("view-View")
    def list(self, request, *args, **kwargs):
        return super(CanvasModelViewSet, self).list(request, *args, **kwargs)

    @HasPermission("view-AddChart")
    def create(self, request, *args, **kwargs):
        response = _execute_with_clean_validation_error(lambda: super(CanvasModelViewSet, self).create(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", ""))
        log_ops_analysis_success(request, response, "create", f"新增{self.canvas_label}: {name}")
        return response

    @HasPermission("view-EditChart")
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "编辑")
        response = _execute_with_clean_validation_error(lambda: super(CanvasModelViewSet, self).update(request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑{self.canvas_label}: {name}")
        return response

    @HasPermission("view-EditChart")
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin_content_update(instance, request)
        response = _execute_with_clean_validation_error(lambda: _partial_update_with_auth(self, request, *args, **kwargs))
        name = get_response_name(response, request.data.get("name", instance.name))
        log_ops_analysis_success(request, response, "update", f"编辑{self.canvas_label}: {name}")
        return response

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        _raise_if_builtin(instance, "删除")
        name = instance.name
        response = super(CanvasModelViewSet, self).destroy(request, *args, **kwargs)
        log_ops_analysis_success(request, response, "delete", f"删除{self.canvas_label}: {name}")
        return response

    @HasPermission("view-View")
    @action(detail=True, methods=["post"], url_path="share")
    def share(self, request, *args, **kwargs):
        if not getattr(self, "share_resource_type", None):
            from rest_framework.exceptions import MethodNotAllowed

            raise MethodNotAllowed("POST")
        return _create_canvas_share_response(
            self,
            request,
            resource_type=self.share_resource_type,
            resource_label=self.canvas_label,
        )


class ScreenModelViewSet(CanvasModelViewSet):
    """
    大屏
    """

    queryset = Screen.objects.all()
    serializer_class = ScreenModelSerializer
    filterset_class = ScreenModelFilter
    permission_key = "directory.screen"
    canvas_label = "大屏"
    share_resource_type = "screen"

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        from apps.operation_analysis.services.canvas_report.types import RESOURCE_TYPE_SCREEN

        return _destroy_subscribable_canvas(
            self,
            request,
            resource_type=RESOURCE_TYPE_SCREEN,
            log_action="删除大屏: {name}",
        )


class ReportModelViewSet(CanvasModelViewSet):
    """
    报表
    """

    queryset = Report.objects.all()
    serializer_class = ReportModelSerializer
    filterset_class = ReportModelFilter
    permission_key = "directory.report"
    canvas_label = "报表"
    share_resource_type = "report"

    @HasPermission("view-DeleteChart")
    def destroy(self, request, *args, **kwargs):
        from apps.operation_analysis.services.canvas_report.types import RESOURCE_TYPE_REPORT

        return _destroy_subscribable_canvas(
            self,
            request,
            resource_type=RESOURCE_TYPE_REPORT,
            log_action="删除报表: {name}",
        )
