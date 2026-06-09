from django.db import transaction
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.permission_utils import get_permission_rules, permission_filter
from apps.core.utils.web_utils import WebUtils
from apps.monitor.constants.permission import PermissionConstants
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    CollectConfig,
    MonitorObjectOrganizationRule,
)
from apps.monitor.services.monitor_instance import InstanceSearch
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.services.monitor_object import MonitorObjectService
from apps.monitor.services.policy_source_cleanup import cleanup_policy_sources
from apps.monitor.services.flow_onboarding import FlowOnboardingService
from apps.monitor.services.effective_plugins import MonitorEffectivePluginService
from apps.monitor.services.metrics import Metrics as MetricsService
from apps.monitor.utils.pagination import parse_page_params
from apps.rpc.node_mgmt import NodeMgmt


def _build_actor_context(request):
    current_team = request.COOKIES.get("current_team")
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")

    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")

    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
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
    if actor_context["is_superuser"]:
        return None

    groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
    if not groups:
        raise UnauthorizedException("当前组织无可用权限范围")
    return groups


def _ensure_target_organizations(organizations, actor_context):
    try:
        normalized_orgs = {int(org) for org in organizations if org not in (None, "")}
    except (TypeError, ValueError):
        raise BaseAppException("组织参数非法")

    if not normalized_orgs or actor_context["is_superuser"]:
        return

    unauthorized_orgs = normalized_orgs - _get_authorized_scope_groups(actor_context)
    if unauthorized_orgs:
        raise UnauthorizedException("无权限关联指定组织")


def _ensure_instance_scope(instance_ids, actor_context):
    normalized_ids = _normalize_id_list(instance_ids)
    if not normalized_ids or actor_context["is_superuser"]:
        return normalized_ids

    allowed_groups = _get_authorized_scope_groups(actor_context)
    instance_org_map = {}
    for instance_id, organization in MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=normalized_ids).values_list(
        "monitor_instance_id", "organization"
    ):
        instance_org_map.setdefault(str(instance_id), set()).add(organization)

    unauthorized_ids = [instance_id for instance_id in normalized_ids if instance_org_map.get(instance_id, set()) - allowed_groups]
    if unauthorized_ids:
        raise UnauthorizedException("无权限操作跨组织监控实例")

    return normalized_ids


def _ensure_operate_instances(request, instance_ids, actor_context=None):
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
    if found_ids != set(normalized_ids):
        raise BaseAppException("监控实例不存在")

    if not actor_context["is_superuser"]:
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

    return _ensure_instance_scope(normalized_ids, actor_context)


class MonitorInstanceViewSet(viewsets.ViewSet):
    @action(methods=["get"], detail=False, url_path="query_params_enum/(?P<name>[^/.]+)")
    def get_query_params_enum(self, request, name):
        data = InstanceSearch.get_query_params_enum(name, request.GET.get("monitor_object_id"))
        return WebUtils.response_success(data)

    @action(methods=["get"], detail=False, url_path="(?P<monitor_object_id>[^/.]+)/list")
    def monitor_instance_list(self, request, monitor_object_id):
        """非特殊对象的通用列表接口"""
        include_children = request.COOKIES.get("include_children", "0") == "1"
        current_team = request.COOKIES.get("current_team")

        permission = get_permission_rules(
            request.user,
            current_team,
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
            include_children=include_children,
        )

        qs = permission_filter(
            MonitorInstance,
            permission,
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

        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
            include_children=include_children,
        )
        qs = permission_filter(
            MonitorInstance,
            permission,
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

        actor_context = _build_actor_context(request)
        _ensure_operate_instances(request, [instance_id], actor_context)
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

        include_children = request.COOKIES.get("include_children", "0") == "1"
        permission = get_permission_rules(
            request.user,
            request.COOKIES.get("current_team"),
            "monitor",
            f"{PermissionConstants.INSTANCE_MODULE}.{monitor_object_id}",
            include_children=include_children,
        )
        qs = permission_filter(
            MonitorInstance,
            permission,
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
        _ensure_target_organizations(request.data.get("organizations", []), actor_context)
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
        _ensure_target_organizations(organizations, actor_context)
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
        _ensure_target_organizations(organizations, actor_context)
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
        _ensure_target_organizations(organizations, actor_context)
        MonitorObjectService.set_instances_organizations(instance_ids, organizations)
        return WebUtils.response_success()
