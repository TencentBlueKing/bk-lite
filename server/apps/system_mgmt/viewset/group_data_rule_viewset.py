from django.http import JsonResponse
from django_filters import filters
from django_filters.rest_framework import FilterSet
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.viewset_utils import LanguageViewSet
from apps.rpc.cmdb import CMDB
from apps.rpc.job_mgmt import JobMgmt
from apps.rpc.log import Log
from apps.rpc.mlops import MLOps
from apps.rpc.monitor import Monitor
from apps.rpc.node_mgmt import NodeMgmt
from apps.rpc.operation_analysis import OperationAnalysisRPC
from apps.rpc.opspilot import OpsPilot
from apps.rpc.system_mgmt import SystemMgmt
from apps.system_mgmt.models import GroupDataRule, UserRule
from apps.system_mgmt.serializers import GroupDataRuleSerializer
from apps.system_mgmt.utils.group_filter_mixin import get_user_group_ids
from apps.system_mgmt.utils.operation_log_utils import log_operation


def _build_actor_context(request, loader=None):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        message = loader.get("error.current_team_required") if loader else "缺少 current_team 参数"
        return None, JsonResponse({"result": False, "message": message}, status=400)

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        message = loader.get("error.invalid_current_team") if loader else "current_team 参数非法"
        return None, JsonResponse({"result": False, "message": message}, status=400)

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }, None


class GroupDataRuleFilter(FilterSet):
    name = filters.CharFilter(field_name="name", lookup_expr="icontains")
    group_id = filters.CharFilter(field_name="group_id", lookup_expr="exact")
    app = filters.CharFilter(field_name="app", lookup_expr="exact")


class GroupDataRuleViewSet(LanguageViewSet):
    """数据权限规则 ViewSet - 禁用未使用的 retrieve/partial_update 接口

    权限校验：
    - 所有接口需要对应的 HasPermission 装饰器
    - list 限制为用户有权限的组的规则
    - create/update/destroy 校验 group_id 属于用户有权限的组
    """

    queryset = GroupDataRule.objects.all().order_by("-id")
    serializer_class = GroupDataRuleSerializer
    filterset_class = GroupDataRuleFilter
    # 仅允许 GET (list, actions), POST (create), PUT (update), DELETE (destroy)
    # 禁用 PATCH (partial_update)
    http_method_names = ["get", "post", "put", "delete", "options"]

    def _get_user_group_ids(self, user):
        """获取用户有权限的组ID集合"""
        return get_user_group_ids(user)

    def _validate_group_permission(self, request, group_id):
        """校验用户是否有权限访问指定组

        Args:
            request: 请求对象
            group_id: 要校验的组ID

        Returns:
            tuple: (is_valid, error_response)
        """
        if getattr(request.user, "is_superuser", False):
            return True, None

        user_group_ids = self._get_user_group_ids(request.user)
        if group_id not in user_group_ids:
            message = self.loader.get("error.no_permission_access_group") if self.loader else "无权访问该组织"
            return False, JsonResponse({"result": False, "message": message}, status=403)
        return True, None

    def _filter_by_accessible_groups(self, queryset, user):
        """按用户有权限的组筛选规则

        Args:
            queryset: 原始查询集
            user: 当前用户对象

        Returns:
            QuerySet: 筛选后的查询集
        """
        if getattr(user, "is_superuser", False):
            return queryset

        user_group_ids = self._get_user_group_ids(user)
        if not user_group_ids:
            return queryset.none()

        # 筛选 group_id 在用户有权限的组中的规则
        return queryset.filter(group_id__in=user_group_ids)

    def retrieve(self, request, *args, **kwargs):
        """禁用内置 retrieve 接口"""
        return JsonResponse({"result": False, "message": self.loader.get("error.api_not_enabled") if self.loader else "接口未启用"}, status=405)

    @HasPermission("data_permission-Delete")
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()

        # 校验用户是否有权限访问该规则所属的组
        is_valid, error_response = self._validate_group_permission(request, obj.group_id)
        if not is_valid:
            return error_response

        rule_name = obj.name
        rule_id = obj.id

        # 获取绑定到此规则的用户，在删除前获取
        affected_users = list(UserRule.objects.filter(group_rule_id=rule_id).values("username", "domain"))

        response = super().destroy(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 204:
            log_operation(request, "delete", "system-manager", f"删除数据权限: {rule_name}")
            # 清除受影响用户的权限缓存
            if affected_users:
                clear_users_permission_cache(affected_users)

        return response

    @HasPermission("data_permission-Add")
    def create(self, request, *args, **kwargs):
        # 校验用户是否有权限访问该规则所属的组
        group_id = request.data.get("group_id")
        if group_id:
            is_valid, error_response = self._validate_group_permission(request, int(group_id))
            if not is_valid:
                return error_response

        response = super().create(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 201:
            rule_name = response.data.get("name", "")
            log_operation(request, "create", "system-manager", f"新增数据权限: {rule_name}")

        return response

    @HasPermission("data_permission-Edit")
    def update(self, request, *args, **kwargs):
        obj = self.get_object()

        # 校验用户是否有权限访问该规则所属的组
        is_valid, error_response = self._validate_group_permission(request, obj.group_id)
        if not is_valid:
            return error_response

        # 如果请求中包含新的 group_id，也需要校验
        new_group_id = request.data.get("group_id")
        if new_group_id and int(new_group_id) != obj.group_id:
            is_valid, error_response = self._validate_group_permission(request, int(new_group_id))
            if not is_valid:
                return error_response

        rule_id = obj.id

        response = super().update(request, *args, **kwargs)

        # 记录操作日志
        if response.status_code == 200:
            rule_name = response.data.get("name", "")
            log_operation(request, "update", "system-manager", f"编辑数据权限: {rule_name}")
            # 清除绑定到此规则的用户的权限缓存
            affected_users = list(UserRule.objects.filter(group_rule_id=rule_id).values("username", "domain"))
            if affected_users:
                clear_users_permission_cache(affected_users)

        return response

    @HasPermission("data_permission-View")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        # 按用户有权限的组筛选
        queryset = self._filter_by_accessible_groups(queryset, request.user)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return JsonResponse({"result": True, "data": serializer.data})

    @action(methods=["GET"], detail=False)
    @HasPermission("data_permission-View")
    def get_app_data(self, request):
        params = request.GET.dict()
        if params.get("app") == "mlops":
            try:
                group_id = int(params.get("group_id"))
            except (TypeError, ValueError):
                return JsonResponse({"result": False, "message": "group_id 参数非法"}, status=400)

            is_valid, error_response = self._validate_group_permission(request, group_id)
            if not is_valid:
                return error_response

            actor_context, error_response = _build_actor_context(request, self.loader)
            if error_response:
                return error_response
            params["actor_context"] = actor_context

        client = self.get_client(params)
        fun = getattr(client, "get_module_data", None)
        if fun is None:
            message = self.loader.get("error.module_not_found") if self.loader else "Module not found"
            raise AttributeError(message)
        params["page"] = int(params.get("page", "1"))
        params["page_size"] = int(params.get("page_size", "10"))
        return_data = fun(**params)
        if isinstance(return_data, dict) and not return_data.get("result", True):
            return JsonResponse({"result": False, "message": return_data.get("message", "")}, status=400)
        return JsonResponse({"result": True, "data": return_data})

    @action(methods=["GET"], detail=False)
    @HasPermission("data_permission-View")
    def get_app_module(self, request):
        params = request.GET.dict()
        client = self.get_client(params)
        fun = getattr(client, "get_module_list", None)
        if fun is None:
            message = self.loader.get("error.module_not_found") if self.loader else "Module not found"
            raise AttributeError(message)
        return_data = fun()
        for i in return_data:
            translated_name = self.loader.get(i["display_name"]) if self.loader else None
            i["display_name"] = translated_name or i["display_name"]
            if "children" in i:
                for child in i["children"]:
                    translated_child_name = self.loader.get(child["display_name"]) if self.loader else None
                    child["display_name"] = translated_child_name or child["display_name"]
        return JsonResponse({"result": True, "data": return_data})

    @staticmethod
    def get_client(params):
        client_map = {
            "opspilot": OpsPilot,
            "system-manager": SystemMgmt,
            "node": NodeMgmt,
            "monitor": Monitor,
            "log": Log,
            "mlops": MLOps,
            "cmdb": CMDB,
            "ops-analysis": OperationAnalysisRPC,
            "job": JobMgmt,
        }
        app = params.pop("app")
        if app not in client_map.keys():
            raise Exception("APP not found")
        client = client_map[app]()
        return client
