from rest_framework import viewsets

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.web_utils import WebUtils
from apps.monitor.filters.monitor_object import MonitorObjectOrganizationRuleFilter
from apps.monitor.models import MonitorObjectOrganizationRule, MonitorInstance, MonitorObject
from apps.monitor.serializers.monitor_object import MonitorObjectOrganizationRuleSerializer
from apps.monitor.services.organization_rule import OrganizationRule
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.monitor.views.monitor_instance import (
    _build_actor_context,
    _ensure_operate_instances,
    _ensure_target_organizations,
)
from config.drf.pagination import CustomPageNumberPagination


def _get_authorized_scope_groups(actor_context):
    if actor_context["is_superuser"]:
        return None

    groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
    if not groups:
        raise UnauthorizedException("当前组织无可用权限范围")
    return groups


def _normalize_rule_organizations(organizations):
    try:
        return {int(org) for org in (organizations or []) if org not in (None, "")}
    except (TypeError, ValueError):
        raise BaseAppException("组织参数非法")


def _rule_is_authorized(rule, actor_context, require_operate=False, authorized_instance_cache=None):
    if actor_context["is_superuser"]:
        return True

    rule_orgs = _normalize_rule_organizations(rule.organizations)
    if not rule_orgs:
        return False

    allowed_groups = _get_authorized_scope_groups(actor_context)
    if rule_orgs - allowed_groups:
        return False

    if not rule.monitor_instance_id:
        return True

    cache_key = (str(rule.monitor_object_id), require_operate)
    if authorized_instance_cache is None:
        authorized_instance_cache = {}

    if cache_key not in authorized_instance_cache:
        authorized_instance_cache[cache_key] = {
            str(instance_id)
            for instance_id in InstanceConfigService._get_authorized_monitor_instances(
                actor_context,
                rule.monitor_object_id,
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


def _validate_rule_payload(request, actor_context, monitor_object_id, monitor_instance_id, organizations):
    _ensure_target_organizations(organizations or [], actor_context)
    if monitor_instance_id not in (None, ""):
        _ensure_operate_instances(request, [monitor_instance_id], actor_context)
        _validate_rule_binding(monitor_object_id, monitor_instance_id)


class MonitorObjectOrganizationRuleViewSet(viewsets.ModelViewSet):
    queryset = MonitorObjectOrganizationRule.objects.all()
    serializer_class = MonitorObjectOrganizationRuleSerializer
    filterset_class = MonitorObjectOrganizationRuleFilter
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset().select_related("monitor_object")
        request = getattr(self, "request", None)
        if request is None:
            return queryset

        actor_context = _build_actor_context(request)
        if actor_context["is_superuser"]:
            return queryset

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
        _validate_rule_payload(
            request,
            actor_context,
            request.data.get("monitor_object", rule.monitor_object_id),
            request.data.get("monitor_instance_id", rule.monitor_instance_id),
            request.data.get("organizations", rule.organizations),
        )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        rule = self.get_object()
        actor_context = _build_actor_context(request)
        _validate_rule_payload(
            request,
            actor_context,
            request.data.get("monitor_object", rule.monitor_object_id),
            request.data.get("monitor_instance_id", rule.monitor_instance_id),
            request.data.get("organizations", rule.organizations),
        )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        del_instance_org = request.query_params.get("del_instance_org", "false").lower() in ["true", "1", "yes"]
        OrganizationRule.del_organization_rule(rule_id=rule.id, del_instance_org=del_instance_org)
        return WebUtils.response_success()
