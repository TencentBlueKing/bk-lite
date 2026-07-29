from rest_framework import viewsets

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.current_team_scope import _normalize_organization_ids
from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_object import MonitorObjectOrganizationRuleFilter
from apps.monitor.models import MonitorInstance, MonitorObject, MonitorObjectOrganizationRule
from apps.monitor.serializers.monitor_object import MonitorObjectOrganizationRuleSerializer
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.services.organization_rule import OrganizationRule
from apps.monitor.views.monitor_instance import _build_actor_context, _ensure_operate_instances, _ensure_target_organizations
from config.drf.pagination import CustomPageNumberPagination


def _get_authorized_scope_groups(actor_context):
    groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
    if not groups:
        raise UnauthorizedException("当前组织无可用权限范围")
    return groups


def _normalize_rule_organizations(organizations):
    return set(_normalize_organization_ids(organizations))


def _rule_is_authorized(rule, actor_context, require_operate=False, authorized_instance_cache=None):
    try:
        rule_orgs = _normalize_rule_organizations(rule.organizations)
    except BaseAppException:
        return False

    allowed_groups = _get_authorized_scope_groups(actor_context)
    if not rule_orgs.intersection(allowed_groups):
        return False

    if not rule.monitor_instance_id:
        return True

    instance_monitor_object_id = MonitorInstance.objects.filter(id=rule.monitor_instance_id).values_list("monitor_object_id", flat=True).first()
    if instance_monitor_object_id is None:
        return False

    cache_key = (str(instance_monitor_object_id), require_operate)
    if authorized_instance_cache is None:
        authorized_instance_cache = {}

    if cache_key not in authorized_instance_cache:
        authorized_instance_cache[cache_key] = {
            str(instance_id)
            for instance_id in InstanceConfigService._get_authorized_monitor_instances(
                actor_context,
                instance_monitor_object_id,
                require_operate=require_operate,
            ).values_list("id", flat=True)
        }

    return str(rule.monitor_instance_id) in authorized_instance_cache[cache_key]


def _validate_rule_binding(monitor_object_id, monitor_instance_id):
    if monitor_instance_id in (None, "") or monitor_object_id in (None, ""):
        return

    instance = MonitorInstance.objects.filter(id=monitor_instance_id).values("monitor_object_id").first()
    if not instance:
        raise BaseAppException("监控实例不存在")
    if str(instance["monitor_object_id"]) == str(monitor_object_id):
        return

    # 兼容 create_default_rule 自动建子规则的设计:子对象(derivative)的规则
    # 会沿用父实例 ID,此时 instance.monitor_object_id 必为 rule.monitor_object.parent_id
    if MonitorObject.objects.filter(id=monitor_object_id, parent_id=instance["monitor_object_id"]).exists():
        return

    raise BaseAppException("监控实例与监控对象不匹配")


def _validate_rule_payload(
    request,
    actor_context,
    monitor_object_id,
    monitor_instance_id,
    organizations,
    *,
    validate_organizations=True,
):
    if validate_organizations:
        _ensure_target_organizations(organizations, actor_context, request)
    if monitor_instance_id not in (None, ""):
        _ensure_operate_instances(request, [monitor_instance_id], actor_context)
        _validate_rule_binding(monitor_object_id, monitor_instance_id)


class MonitorObjectOrganizationRuleViewSet(viewsets.ModelViewSet):
    queryset = MonitorObjectOrganizationRule.objects.all()
    serializer_class = MonitorObjectOrganizationRuleSerializer
    filterset_class = MonitorObjectOrganizationRuleFilter
    pagination_class = CustomPageNumberPagination

    def _get_actor_context(self):
        if not hasattr(self, "_actor_context_cache"):
            self._actor_context_cache = _build_actor_context(self.request)
        return self._actor_context_cache

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["data_team_ids"] = self._get_actor_context()["data_scope"].data_team_ids
        return context

    def get_queryset(self):
        queryset = super().get_queryset().select_related("monitor_object")
        request = getattr(self, "request", None)
        if request is None:
            return queryset

        actor_context = self._get_actor_context()

        require_operate = getattr(self, "action", "") in {"update", "partial_update", "destroy"}
        authorized_instance_cache = {}
        allowed_ids = [
            rule.id
            for rule in queryset
            if _rule_is_authorized(
                rule,
                actor_context,
                require_operate=require_operate,
                authorized_instance_cache=authorized_instance_cache,
            )
        ]

        if not allowed_ids:
            return queryset.none()
        return queryset.filter(id__in=allowed_ids)

    def create(self, request, *args, **kwargs):
        actor_context = _build_actor_context(request)
        _validate_rule_payload(
            request,
            actor_context,
            request.data.get("monitor_object"),
            request.data.get("monitor_instance_id"),
            request.data.get("organizations", []),
        )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        rule = self.get_object()
        actor_context = _build_actor_context(request)
        is_partial = kwargs.get("partial", False)
        _validate_rule_payload(
            request,
            actor_context,
            request.data.get("monitor_object", rule.monitor_object_id),
            request.data.get("monitor_instance_id", rule.monitor_instance_id),
            request.data.get("organizations"),
            validate_organizations=not is_partial or "organizations" in request.data,
        )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        del_instance_org = request.query_params.get("del_instance_org", "false").lower() in ["true", "1", "yes"]
        OrganizationRule.del_organization_rule(rule_id=rule.id, del_instance_org=del_instance_org)
        return WebUtils.response_success()
