from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope, scope_permission_queryset, validate_assignable_organizations
from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorInstanceOrganization, MonitorObject, MonitorObjectOrganizationRule
from apps.monitor.services.effective_plugins import MonitorEffectivePluginService
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.metrics import Metrics as MetricsService
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.services.policy_source_cleanup import cleanup_policy_sources
from apps.monitor.utils.dimension import normalize_instance_identity
from apps.monitor.utils.pagination import parse_page_params
from apps.rpc.node_mgmt import NodeMgmt


def _build_actor_context(request):
    scope = resolve_current_team_data_scope(request)

    return {
        "username": scope.username,
        "domain": scope.domain,
        "current_team": scope.current_team,
        "include_children": scope.include_children,
        "is_superuser": scope.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
        "data_scope": scope,
        "request": request,
    }


def _normalize_id_list(values):
    normalized_ids = []
    seen_ids = set()
    for value in values:
        if value in (None, ""):
            continue
        normalized_id = str(value)
        if normalized_id in seen_ids:
            continue
        seen_ids.add(normalized_id)
        normalized_ids.append(normalized_id)
    return normalized_ids


def _get_authorized_scope_groups(actor_context):
    groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
    if not groups:
        raise UnauthorizedException("当前组织无可用权限范围")
    return groups


def _ensure_target_organizations(organizations, actor_context, request=None):
    if not organizations:
        return

    request = request or actor_context.get("request")
    if request is None:
        raise BaseAppException("缺少组织分配请求上下文")
    validate_assignable_organizations(request, organizations)


def _ensure_instance_scope(instance_ids, actor_context):
    normalized_ids = _normalize_id_list(instance_ids)
    if not normalized_ids:
        return normalized_ids

    allowed_groups = _get_authorized_scope_groups(actor_context)
    instance_org_map = {}
    for instance_id, organization in MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=normalized_ids).values_list(
        "monitor_instance_id", "organization"
    ):
        instance_org_map.setdefault(str(instance_id), set()).add(organization)

    unauthorized_ids = [instance_id for instance_id in normalized_ids if not instance_org_map.get(instance_id, set()).intersection(allowed_groups)]
    if unauthorized_ids:
        raise UnauthorizedException("无权限操作跨组织监控实例")

    return normalized_ids


def _ensure_operate_instances(request, instance_ids, actor_context=None, allow_missing=False):
    normalized_ids = _normalize_id_list(instance_ids)
    if not normalized_ids:
        return []

    actor_context = actor_context or _build_actor_context(request)
    instances = list(
        MonitorInstance.objects.filter(id__in=normalized_ids).values(
            "id",
            "monitor_object_id",
        )
    )
    found_ids = {str(instance["id"]) for instance in instances}
    # allow_missing: derived / auto-discovered instances (e.g. K8s Pod and Node)
    # report metrics under an instance_id that has no MonitorInstance row. Read-only
    # endpoints (e.g. effective_plugins) must tolerate their absence instead of 500-ing;
    # only the instances that DO have a row are authorization-scoped below. Mutating
    # callers keep allow_missing=False so a bogus instance_id still fails fast.
    if found_ids != set(normalized_ids) and not allow_missing:
        raise BaseAppException("监控实例不存在")

    instances_by_object = {}
    for instance in instances:
        instances_by_object.setdefault(instance["monitor_object_id"], set()).add(str(instance["id"]))

    for monitor_object_id, requested_ids in instances_by_object.items():
        allowed_ids = {
            str(instance_id)
            for instance_id in InstanceConfigService._get_authorized_monitor_instances(
                actor_context,
                monitor_object_id,
                require_operate=True,
            )
            .filter(id__in=requested_ids)
            .values_list("id", flat=True)
        }
        if requested_ids - allowed_ids:
            raise UnauthorizedException("无权限操作指定监控实例")

    if found_ids:
        _ensure_instance_scope(found_ids, actor_context)
    return normalized_ids


class MonitorInstanceViewSet(viewsets.ViewSet):
    @action(methods=["get"], detail=False, url_path="query_params_enum/(?P<name>[^/.]+)")
    def get_query_params_enum(self, request, name):
        data = InstanceSearch.get_query_params_enum(name, request.GET.get("monitor_object_id"))
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="(?P<monitor_object_id>[^/.]+)/list")
    def monitor_instance_list(self, request, monitor_object_id):
        """非特殊对象的通用列表接口"""
        scope = resolve_current_team_data_scope(request)
        permission = (
            {"team": list(scope.data_team_ids), "instance": []}
            if request.user.is_superuser
            else get_permission_rules(
                request.user,
                scope.current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
                include_children=scope.include_children,
            )
        )

        qs = scope_permission_queryset(
            MonitorInstance,
            permission,
            scope,
            team_key="monitorinstanceorganization__organization__in",
            id_key="id__in",
        )
        page, page_size = parse_page_params(
            request.GET,
            default_page=1,
            default_page_size=10,
            allow_page_size_all=True,
        )
        add_metrics = str(request.GET.get("add_metrics", "")).lower() in (
            "1",
            "true",
            "yes",
        )
        data = MonitorObjectService.get_monitor_instance(
            int(monitor_object_id),
            page,
            page_size,
            request.GET.get("name"),
            qs,
            add_metrics,
            request.GET.get("monitor_plugin_id"),
        )
        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for instance_info in data["results"]:
            if instance_info["instance_id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["instance_id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        if add_metrics:
            MetricsService.convert_instance_list_metrics(int(monitor_object_id), data["results"])

        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="(?P<monitor_object_id>[^/.]+)/search")
    def monitor_instance_search(self, request, monitor_object_id):
        """特殊搜索接口，特殊对象不通用的查询条件"""

        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")

        scope = resolve_current_team_data_scope(request)
        permission = (
            {"team": list(scope.data_team_ids), "instance": []}
            if request.user.is_superuser
            else get_permission_rules(
                request.user,
                scope.current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
                include_children=scope.include_children,
            )
        )
        qs = scope_permission_queryset(
            MonitorInstance,
            permission,
            scope,
            team_key="monitorinstanceorganization__organization__in",
            id_key="id__in",
        )

        search_obj = InstanceSearch(
            monitor_obj,
            dict(**request.data),
            qs=qs,
            locale=request.user.locale,
        )
        data = search_obj.search()
        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for instance_info in data["results"]:
            if instance_info["instance_id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["instance_id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION

        if request.data.get("add_metrics"):
            MetricsService.convert_instance_list_metrics(int(monitor_object_id), data["results"])

        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="(?P<monitor_object_id>[^/.]+)/effective_plugins")
    def effective_plugins(self, request, monitor_object_id):
        instance_id = request.GET.get("instance_id")
        if not instance_id:
            raise BaseAppException("instance_id is required")

        # 前端下传的可能是干净标量(如 "mssql_1433"),也可能是完整 tuple 串
        # (如 VMware ESXi 的 "('vcenter-a', 'host-3171')")。统一归一为存储键形态：
        # - 单维实例补齐为 "('mssql_1433',)"
        # - 多维实例保持完整 tuple
        # 这样既匹配存在性校验,也保证 get_effective_plugins 内部按存储键比对上报数据,
        # 避免误报"监控实例不存在"。
        instance_id = normalize_instance_identity(instance_id)["storage_instance_key"]

        actor_context = _build_actor_context(request)
        # Derived instances (K8s Pod/Node) have no MonitorInstance row; tolerate their
        # absence so the detail view resolves plugins from reported metrics instead of 500-ing.
        _ensure_operate_instances(request, [instance_id], actor_context, allow_missing=True)
        data = MonitorEffectivePluginService.get_effective_plugins(
            int(monitor_object_id),
            instance_id,
            getattr(request.user, "locale", "zh-Hans"),
        )
        return WebUtils.response_success(data)

    @action(
        methods=["post"],
        detail=False,
        url_path="(?P<monitor_object_id>[^/.]+)/list_by_primary_object",
    )
    def list_by_primary_object(self, request, monitor_object_id):
        monitor_obj = MonitorObject.objects.filter(id=monitor_object_id).first()
        if not monitor_obj:
            raise BaseAppException("Monitor object does not exist")
        if monitor_obj.parent_id:
            raise BaseAppException("Only primary monitor objects support instance search")

        scope = resolve_current_team_data_scope(request)
        permission = (
            {"team": list(scope.data_team_ids), "instance": []}
            if request.user.is_superuser
            else get_permission_rules(
                request.user,
                scope.current_team,
                "monitor",
                f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
                include_children=scope.include_children,
            )
        )
        qs = scope_permission_queryset(
            MonitorInstance,
            permission,
            scope,
            team_key="monitorinstanceorganization__organization__in",
            id_key="id__in",
        )

        search_obj = InstanceSearch(
            monitor_obj,
            dict(**request.data),
            qs=qs,
            locale=request.user.locale,
        )
        data = search_obj.search_by_primary_object()
        # 如果有权限规则，则添加到数据中
        inst_permission_map = {i["id"]: i["permission"] for i in permission.get("instance", [])}
        for instance_info in data["results"]:
            if instance_info["instance_id"] in inst_permission_map:
                instance_info["permission"] = inst_permission_map[instance_info["instance_id"]]
            else:
                instance_info["permission"] = PermissionConstants.DEFAULT_PERMISSION
        return WebUtils.response_success(data)

    @action(
        methods=["post"],
        detail=False,
        url_path="(?P<monitor_object_id>[^/.]+)/generate_instance_id",
    )
    def generate_monitor_instance_id(self, request, monitor_object_id):
        result = MonitorObjectService.generate_monitor_instance_id(
            int(monitor_object_id),
            request.data["monitor_instance_name"],
            request.data["interval"],
        )
        return WebUtils.response_success(result)

    @action(
        methods=["post"],
        detail=False,
        url_path="(?P<monitor_object_id>[^/.]+)/check_monitor_instance",
    )
    def check_monitor_instance(self, request, monitor_object_id):
        MonitorObjectService.check_monitor_instance(int(monitor_object_id), request.data)
        return WebUtils.response_success()

    @action(methods=["get"], detail=False, url_path="autodiscover_monitor_instance")
    def autodiscover_monitor_instance(self, request):
        MonitorObjectService.autodiscover_monitor_instance()
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="remove_monitor_instance")
    def remove_monitor_instance(self, request):
        actor_context = _build_actor_context(request)
        instance_ids = _ensure_operate_instances(
            request,
            request.data.get("instance_ids", []),
            actor_context,
        )
        with transaction.atomic():
            refresh_region_ids = list(
                dict.fromkeys(
                    MonitorInstance.objects.select_for_update()
                    .filter(
                        id__in=instance_ids,
                        cloud_region_id__isnull=False,
                        monitor_object__name__in=FlowOnboardingService.SUPPORTED_MONITOR_OBJECT_NAMES,
                    )
                    .exclude(enabled_protocols=[])
                    .values_list("cloud_region_id", flat=True)
                )
            )
            MonitorInstance.objects.filter(id__in=instance_ids).update(is_deleted=True)
            config_objs = CollectConfig.objects.filter(monitor_instance_id__in=instance_ids)
            child_configs, configs = [], []
            for config in config_objs:
                if config.is_child:
                    child_configs.append(config.id)
                else:
                    configs.append(config.id)
            # 删除子配置
            NodeMgmt().delete_child_configs(child_configs)
            # 删除配置
            NodeMgmt().delete_configs(configs)
            # 删除配置对象
            config_objs.delete()

            MonitorObjectOrganizationRule.objects.filter(monitor_instance_id__in=instance_ids).delete()
            FlowOnboardingService._schedule_region_refresh(*refresh_region_ids)

        cleanup_policy_sources(instance_ids)

        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="update_monitor_instance")
    def update_monitor_instance(self, request):
        actor_context = _build_actor_context(request)
        _ensure_operate_instances(
            request,
            [request.data.get("instance_id")],
            actor_context,
        )
        _ensure_target_organizations(request.data.get("organizations", []), actor_context, request)
        MonitorObjectService.update_instance(
            request.data.get("instance_id"),
            request.data.get("name"),
            request.data.get("organizations", []),
        )
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="instances_remove_organizations")
    def instances_remove_organizations(self, request):
        """删除监控对象实例组织"""
        actor_context = _build_actor_context(request)
        instance_ids = _ensure_operate_instances(
            request,
            request.data.get("instance_ids", []),
            actor_context,
        )
        organizations = request.data.get("organizations", [])
        _ensure_target_organizations(organizations, actor_context, request)
        MonitorObjectService.remove_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="instances_add_organizations")
    def instances_add_organizations(self, request):
        """添加监控对象实例组织"""
        actor_context = _build_actor_context(request)
        instance_ids = _ensure_operate_instances(
            request,
            request.data.get("instance_ids", []),
            actor_context,
        )
        organizations = request.data.get("organizations", [])
        _ensure_target_organizations(organizations, actor_context, request)
        MonitorObjectService.add_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()

    @action(methods=["post"], detail=False, url_path="set_instances_organizations")
    def set_instances_organizations(self, request):
        """设置监控对象实例组织"""
        actor_context = _build_actor_context(request)
        instance_ids = _ensure_operate_instances(
            request,
            request.data.get("instance_ids", []),
            actor_context,
        )
        organizations = request.data.get("organizations", [])
        _ensure_target_organizations(organizations, actor_context, request)
        MonitorObjectService.set_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()
