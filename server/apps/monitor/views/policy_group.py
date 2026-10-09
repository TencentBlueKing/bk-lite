from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.web_utils import WebUtils
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyTemplate,
)
from apps.monitor.services.policy_group import PolicyGroupService


def _operator(scope):
    return scope.username or "system"


def _group_in_scope(scope, group_id):
    group = (
        PolicyGroup.objects.filter(id=group_id, organization=int(scope.current_team))
        .select_related("monitor_object")
        .first()
    )
    if group is None:
        raise BaseAppException("策略组不存在")
    return group


def _serialize_group(group, default_id, metric_names=None):
    member_count = getattr(group, "joined_member_count", None)
    if member_count is None:
        member_count = group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).count()
    rules = []
    for rule in group.rules.select_related("plugin", "policy"):
        metric_id = PolicyGroupService.metric_id_for_policy(rule.policy)
        metric_name = ""
        if metric_id and metric_names is not None:
            metric_name = metric_names.get(metric_id) or ""
        rules.append(
            {
                "id": rule.id,
                "name": rule.name,
                "plugin_id": rule.plugin_id,
                "plugin_name": rule.plugin.name,
                "metric_name": metric_name,
                "threshold": rule.policy.threshold,
                "notice_users": rule.policy.notice_users or [],
                "policy_id": rule.policy_id,
            }
        )
    return {
        "id": group.id,
        "name": group.name,
        "origin": group.origin,
        "monitor_object_id": group.monitor_object_id,
        "is_default": group.id == default_id,
        "member_count": member_count,
        "rules": rules,
    }


def _legacy_policies(instance):
    found = []
    policies = MonitorPolicy.objects.filter(monitor_object_id=instance.monitor_object_id, group_rule__isnull=True).only("id", "name", "enable", "source")
    for policy in policies:
        values = (policy.source or {}).get("values") or []
        if instance.id in values:
            found.append({"id": policy.id, "name": policy.name, "enable": policy.enable})
    return found


class PolicyGroupViewSet(viewsets.ViewSet):
    def list(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        object_id = request.query_params.get("monitor_object_id")
        if object_id not in (None, "") and request.query_params.get("create_default", "true") != "false":
            monitor_object = MonitorObject.objects.filter(id=object_id).first()
            if monitor_object is not None:
                PolicyGroupService.ensure_default(organization=organization, monitor_object=monitor_object, operator=_operator(scope))
        queryset = PolicyGroup.objects.filter(organization=organization).prefetch_related(
            "rules__plugin", "rules__policy"
        ).annotate(
            joined_member_count=Count("memberships", filter=Q(memberships__state=PolicyGroupMembership.STATE_MEMBER))
        )
        if object_id not in (None, ""):
            queryset = queryset.filter(monitor_object_id=object_id)
        default_id = None
        if object_id not in (None, ""):
            pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object_id=object_id).first()
            default_id = pointer.policy_group_id if pointer else None
        groups = list(queryset.order_by("id"))
        policies = [rule.policy for group in groups for rule in group.rules.all()]
        metric_names = PolicyGroupService.metric_names_for_policies(policies)
        data = []
        for group in groups:
            for rule in group.rules.all():
                PolicyGroupService.ensure_scan_task(rule.policy)
            data.append(_serialize_group(group, default_id, metric_names))
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="create_from_templates")
    @HasPermission("strategy_list-Edit")
    def create_from_templates(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        templates = list(PolicyTemplate.objects.filter(id__in=request.data.get("template_ids") or []).select_related("plugin", "monitor_object"))
        if not templates:
            raise BaseAppException("至少选择一条策略模板")
        monitor_object = templates[0].monitor_object
        group = PolicyGroupService.create_from_templates(
            organization=organization,
            monitor_object=monitor_object,
            name=request.data.get("name") or "新建策略组",
            templates=templates,
            operator=_operator(scope),
        )
        return WebUtils.response_success({"id": group.id, "member_count": 0})

    @action(methods=["post"], detail=False)
    @HasPermission("strategy_list-Edit")
    def join(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        instance_ids = request.data.get("instance_ids") or []
        count = 0
        for instance in MonitorInstance.objects.filter(id__in=instance_ids, monitor_object_id=group.monitor_object_id):
            PolicyGroupService.join(instance=instance, group=group, operator=_operator(scope))
            count += 1
        return WebUtils.response_success({"count": count})

    @action(methods=["post"], detail=False)
    @HasPermission("strategy_list-Edit")
    def leave(self, request):
        scope = resolve_current_team_data_scope(request)
        instance_ids = request.data.get("instance_ids") or []
        allowed = set(
            MonitorInstanceOrganization.objects.filter(
                monitor_instance_id__in=instance_ids,
                organization=int(scope.current_team),
            ).values_list("monitor_instance_id", flat=True)
        )
        count = 0
        for instance in MonitorInstance.objects.filter(id__in=allowed):
            PolicyGroupService.leave(instance=instance, operator=_operator(scope))
            count += 1
        return WebUtils.response_success({"count": count})

    @action(methods=["get"], detail=False)
    def members(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.query_params.get("group_id"))
        rows = []
        memberships = group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).select_related("monitor_instance")
        for membership in memberships:
            instance = membership.monitor_instance
            rows.append(
                {
                    "instance_id": instance.id,
                    "name": instance.name,
                    "state": membership.state,
                    "legacy_policies": _legacy_policies(instance),
                }
            )
        return WebUtils.response_success(rows)

    @action(methods=["get"], detail=False)
    def membership(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        instance = MonitorInstance.objects.filter(id=request.query_params.get("instance_id")).first()
        if instance is None:
            raise BaseAppException("实例不存在")
        if not MonitorInstanceOrganization.objects.filter(monitor_instance=instance, organization=organization).exists():
            raise BaseAppException("实例不属于当前组织")
        membership = PolicyGroupMembership.objects.filter(monitor_instance=instance).select_related("policy_group").first()
        pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object_id=instance.monitor_object_id).first()
        default_id = pointer.policy_group_id if pointer else None
        groups = [
            {"id": group.id, "name": group.name, "is_default": group.id == default_id}
            for group in PolicyGroup.objects.filter(organization=organization, monitor_object_id=instance.monitor_object_id).order_by("id")
        ]
        templates = PolicyTemplate.objects.filter(monitor_object_id=instance.monitor_object_id).filter(
            Q(template_type=PolicyTemplate.TYPE_BUILTIN) | Q(organization=organization)
        )
        return WebUtils.response_success(
            {
                "state": membership.state if membership else None,
                "group_id": membership.policy_group_id if membership else None,
                "group_name": membership.policy_group.name if membership and membership.policy_group_id else "",
                "groups": groups,
                "legacy_policies": _legacy_policies(instance),
                "templates": [{"id": item.id, "name": item.name} for item in templates.order_by("id")],
            }
        )

    @action(methods=["post"], detail=False, url_path="update_rule")
    @HasPermission("strategy_list-Edit")
    def update_rule(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        rule = group.rules.select_related("policy").filter(id=request.data.get("rule_id")).first()
        if rule is None:
            raise BaseAppException("规则不存在")
        PolicyGroupService.update_rule(
            rule,
            threshold=request.data.get("threshold", rule.policy.threshold),
            notice_users=request.data.get("notice_users", rule.policy.notice_users),
            operator=_operator(scope),
        )
        return WebUtils.response_success({"id": rule.id})

    @action(methods=["post"], detail=False, url_path="copy_group")
    @HasPermission("strategy_list-Edit")
    def copy_group(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        copied = PolicyGroupService.copy_group(group, name=request.data.get("name") or f"{group.name} 副本", operator=_operator(scope))
        return WebUtils.response_success({"id": copied.id})

    @action(methods=["post"], detail=False, url_path="set_default")
    @HasPermission("strategy_list-Edit")
    def set_default(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        PolicyGroupService.set_default(group, operator=_operator(scope))
        return WebUtils.response_success({"id": group.id})

    @action(methods=["post"], detail=False, url_path="delete_group")
    @HasPermission("strategy_list-Edit")
    def delete_group(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        PolicyGroupService.delete_group(group, operator=_operator(scope))
        return WebUtils.response_success({})

    @action(methods=["post"], detail=False, url_path="create_standalone")
    @HasPermission("strategy_list-Edit")
    def create_standalone(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        instance = MonitorInstance.objects.filter(id=request.data.get("instance_id")).first()
        if instance is None or not MonitorInstanceOrganization.objects.filter(monitor_instance=instance, organization=organization).exists():
            raise BaseAppException("实例不存在")
        template = PolicyTemplate.objects.filter(id=request.data.get("template_id"), monitor_object_id=instance.monitor_object_id).first()
        if template is None:
            raise BaseAppException("策略模板不存在")
        policy = PolicyGroupService.create_standalone(instance=instance, template=template, operator=_operator(scope), organization=organization)
        return WebUtils.response_success({"id": policy.id})
