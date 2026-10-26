import json

from django.db.models import Count, Q
from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.decorators.api_permission import HasPermission
from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.web_utils import WebUtils
from apps.monitor.models import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyTemplate,
)
from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer
from apps.monitor.services.policy_group import PolicyGroupService, group_detection_state, no_data_carrier_rule_ids
from apps.monitor.utils.pagination import parse_page_params
from apps.system_mgmt.utils.operation_log_utils import log_operation


def _operator(scope):
    return scope.username or "system"


def _group_in_scope(scope, group_id):
    group = PolicyGroup.objects.filter(id=group_id, organization=int(scope.current_team)).select_related("monitor_object").first()
    if group is None:
        raise BaseAppException("策略组不存在")
    return group


def _optional_positive_id(raw, param_name):
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationAppException(f"{param_name} 必须为正整数") from exc
    if value <= 0:
        raise ValidationAppException(f"{param_name} 必须为正整数")
    return value


def _serialize_rule(rule, metric_names=None, alert_counts=None, no_data_carrier=False):
    metric_id = PolicyGroupService.metric_id_for_policy(rule.policy)
    metric_name = ""
    if metric_id and metric_names is not None:
        metric_name = metric_names.get(metric_id) or ""
    metric_name_list = []
    if metric_names is not None:
        metric_name_list = [metric_names[item] for item in PolicyGroupService.metric_ids_for_policy(rule.policy) if item in metric_names]
    query = rule.policy.query_condition if isinstance(rule.policy.query_condition, dict) else {}
    condition_thresholds = {}
    if query.get("type") == "multi":
        condition_thresholds = {item.get("ref"): item.get("threshold") or [] for item in query.get("queries") or [] if isinstance(item, dict)}
    plugin = rule.plugin
    counts = alert_counts or {}
    return {
        "id": rule.id,
        "name": rule.name,
        "plugin_id": rule.plugin_id,
        "plugin_name": plugin.name,
        "collect_type": plugin.collect_type or rule.policy.collect_type or "",
        "metric_name": metric_name,
        "metric_names": metric_name_list,
        "query_type": query.get("type") or "",
        "condition_thresholds": condition_thresholds,
        "threshold": rule.policy.threshold,
        "alert_name": rule.policy.alert_name or "",
        "trigger_count": rule.policy.trigger_count,
        "recovery_condition": rule.policy.recovery_condition,
        "recovery_threshold": rule.policy.recovery_threshold or {},
        "no_data_carrier": bool(no_data_carrier),
        "policy_id": rule.policy_id,
        "open_alert_count": counts.get(rule.policy_id, 0),
    }


def _serialize_group(group, default_id, metric_names=None, plugin_id=None, collect_type=None, alert_counts=None):
    member_count = getattr(group, "joined_member_count", None)
    if member_count is None:
        member_count = group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).count()
    loaded_rules = list(group.rules.select_related("plugin", "policy"))
    visible_rules = PolicyGroupService.filter_rules_for_access(loaded_rules, plugin_id=plugin_id, collect_type=collect_type)
    carrier_ids = no_data_carrier_rule_ids(loaded_rules)
    rules = [_serialize_rule(rule, metric_names, alert_counts, no_data_carrier=rule.id in carrier_ids) for rule in visible_rules]
    counts = alert_counts or {}
    open_alert_count = sum(counts.get(rule.policy_id, 0) for rule in loaded_rules)
    notice = _group_notice(loaded_rules)
    enable = _group_enable(loaded_rules)
    detection = group_detection_state(loaded_rules)
    return {
        "id": group.id,
        "name": group.name,
        "origin": group.origin,
        "monitor_object_id": group.monitor_object_id,
        "is_default": group.id == default_id,
        "member_count": member_count,
        "open_alert_count": open_alert_count,
        "rules": rules,
        **notice,
        **enable,
        **detection,
    }


def _handler_ids(policy):
    return tuple(str(item) for item in (policy.handlers or []))


def _group_notice(rules):
    policies = [rule.policy for rule in rules]
    if not policies:
        return {
            "notice": False,
            "notice_type": "",
            "notice_type_ids": [],
            "notice_users": [],
            "notice_uniform": True,
            "handlers": [],
            "handlers_uniform": True,
        }

    def snapshot(policy):
        return (
            bool(policy.notice),
            policy.notice_type or "",
            tuple(policy.notice_type_ids or []),
            tuple(str(item) for item in (policy.notice_users or [])),
        )

    first = policies[0]
    notice_uniform = all(snapshot(policy) == snapshot(first) for policy in policies)
    handlers_uniform = all(_handler_ids(policy) == _handler_ids(first) for policy in policies)
    if notice_uniform:
        notice = {
            "notice": bool(first.notice),
            "notice_type": first.notice_type or "",
            "notice_type_ids": list(first.notice_type_ids or []),
            "notice_users": list(first.notice_users or []),
            "notice_uniform": True,
        }
    else:
        notice = {
            "notice": False,
            "notice_type": "",
            "notice_type_ids": [],
            "notice_users": [],
            "notice_uniform": False,
        }
    return {
        **notice,
        "handlers": list(first.handlers or []) if handlers_uniform else [],
        "handlers_uniform": handlers_uniform,
    }


def _group_enable(rules):
    policies = [rule.policy for rule in rules]
    if not policies:
        return {"enable": True, "enable_uniform": True}
    flags = [bool(policy.enable) for policy in policies]
    if any(flag != flags[0] for flag in flags):
        return {"enable": False, "enable_uniform": False}
    return {"enable": flags[0], "enable_uniform": True}


def _serialize_groups(groups, default_id, plugin_id=None, collect_type=None):
    policies = [rule.policy for group in groups for rule in group.rules.all()]
    metric_names = PolicyGroupService.metric_names_for_policies(policies)
    alert_counts = PolicyGroupService.open_alert_counts([policy.id for policy in policies])
    data = []
    for group in groups:
        for rule in group.rules.all():
            PolicyGroupService.ensure_scan_task(rule.policy)
        data.append(
            _serialize_group(
                group,
                default_id,
                metric_names,
                plugin_id=plugin_id,
                collect_type=collect_type,
                alert_counts=alert_counts,
            )
        )
    return data


def _legacy_policies(instance):
    return PolicyGroupService.legacy_policies(instance)


class PolicyGroupViewSet(viewsets.ViewSet):
    def list(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        object_id = request.query_params.get("monitor_object_id")
        if object_id not in (None, "") and request.query_params.get("create_default", "true") != "false":
            monitor_object = MonitorObject.objects.filter(id=object_id).first()
            if monitor_object is not None:
                PolicyGroupService.ensure_default(organization=organization, monitor_object=monitor_object, operator=_operator(scope))
        queryset = (
            PolicyGroup.objects.filter(organization=organization)
            .prefetch_related("rules__plugin", "rules__policy")
            .annotate(joined_member_count=Count("memberships", filter=Q(memberships__state=PolicyGroupMembership.STATE_MEMBER)))
        )
        if object_id not in (None, ""):
            queryset = queryset.filter(monitor_object_id=object_id)
        name = str(request.query_params.get("name") or "").strip()
        if name:
            queryset = queryset.filter(name__icontains=name)
        queryset = queryset.order_by("-id")
        default_id = None
        if object_id not in (None, ""):
            pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object_id=object_id).first()
            default_id = pointer.policy_group_id if pointer else None
        plugin_id = _optional_positive_id(request.query_params.get("plugin_id"), "plugin_id")
        collect_type = str(request.query_params.get("collect_type") or "").strip() or None
        if request.query_params.get("page") not in (None, ""):
            page, page_size = parse_page_params(request.GET, default_page=1, default_page_size=20)
            count = queryset.count()
            start = (page - 1) * page_size
            groups = list(queryset[start : start + page_size])
            return WebUtils.response_success(
                {
                    "count": count,
                    "items": _serialize_groups(groups, default_id, plugin_id=plugin_id, collect_type=collect_type),
                }
            )
        return WebUtils.response_success(_serialize_groups(list(queryset), default_id, plugin_id=plugin_id, collect_type=collect_type))

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
        log_operation(
            request,
            "update",
            "monitor",
            "实例加入策略组",
            target_type="policy_group",
            target_id=group.id,
            detail={"group_id": group.id, "count": count},
        )
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
        log_operation(
            request,
            "update",
            "monitor",
            "实例退出策略组",
            target_type="policy_group",
            target_id="",
            detail={"count": count},
        )
        return WebUtils.response_success({"count": count})

    @action(methods=["get"], detail=False)
    def members(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.query_params.get("group_id"))
        memberships = list(group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).select_related("monitor_instance"))
        rows = [
            {
                "instance_id": membership.monitor_instance.id,
                "name": membership.monitor_instance.name,
            }
            for membership in memberships
        ]
        return WebUtils.response_success(rows)

    @action(methods=["get"], detail=False)
    def instance_groups(self, request):
        scope = resolve_current_team_data_scope(request)
        raw = request.query_params.get("instance_ids") or "[]"
        try:
            instance_ids = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            raise BaseAppException("instance_ids 无效")
        if not isinstance(instance_ids, list):
            raise BaseAppException("instance_ids 无效")
        instance_ids = [str(item) for item in instance_ids if str(item).strip()]
        if len(instance_ids) > 100:
            raise BaseAppException("一次最多查询 100 个实例")
        found = PolicyGroupService.member_group_names(instance_ids, int(scope.current_team))
        rows = [{"instance_id": instance_id, "group_id": item["id"], "group_name": item["name"]} for instance_id, item in found.items()]
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
        update_kwargs = {"operator": _operator(scope)}
        if "condition_thresholds" in request.data:
            update_kwargs["condition_thresholds"] = request.data.get("condition_thresholds")
        elif "threshold" in request.data:
            update_kwargs["threshold"] = request.data.get("threshold")
        for field in ("trigger_count", "recovery_condition", "recovery_threshold", "alert_name"):
            if field in request.data:
                update_kwargs[field] = request.data.get(field)
        PolicyGroupService.update_rule(rule, **update_kwargs)
        log_operation(
            request,
            "update",
            "monitor",
            "修改策略组规则",
            target_type="policy_group",
            target_id=group.id,
            detail={"group_id": group.id, "rule_id": rule.id, "policy_id": rule.policy_id},
        )
        return WebUtils.response_success({"id": rule.id})

    @action(methods=["get"], detail=False, url_path="rule_editor")
    def rule_editor(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.query_params.get("group_id"))
        rule = group.rules.select_related("policy").filter(id=request.query_params.get("rule_id")).first()
        if rule is None:
            raise BaseAppException("规则不存在")
        data = MonitorPolicySerializer(rule.policy).data
        data["name"] = rule.name
        data["rule_id"] = rule.id
        data["group_id"] = group.id
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False, url_path="save_rule_editor")
    @HasPermission("strategy_list-Edit")
    def save_rule_editor(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        rule = group.rules.select_related("policy").filter(id=request.data.get("rule_id")).first()
        if rule is None:
            raise BaseAppException("规则不存在")
        closes_alerts = PolicyGroupService.apply_rule_editor(rule, request.data, operator=_operator(scope))
        log_operation(
            request,
            "update",
            "monitor",
            "修改策略组规则",
            target_type="policy_group",
            target_id=group.id,
            detail={"group_id": group.id, "rule_id": rule.id, "policy_id": rule.policy_id},
        )
        return WebUtils.response_success({"id": rule.id, "closes_alerts": closes_alerts})

    @action(methods=["post"], detail=False, url_path="update_detection")
    @HasPermission("strategy_list-Edit")
    def update_detection(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        has_schedule = "schedule" in request.data
        has_no_data = "no_data" in request.data
        if not has_schedule and not has_no_data:
            raise ValidationAppException("请至少设置检测频率或无数据告警")
        PolicyGroupService.update_detection(
            group,
            schedule=request.data.get("schedule") if has_schedule else None,
            no_data=request.data.get("no_data") if has_no_data else None,
            operator=_operator(scope),
        )
        log_operation(
            request,
            "update",
            "monitor",
            "修改策略组检测配置",
            target_type="policy_group",
            target_id=group.id,
            detail={"group_id": group.id, "schedule": has_schedule, "no_data": has_no_data},
        )
        return WebUtils.response_success({"id": group.id})

    @action(methods=["post"], detail=False, url_path="update_notice")
    @HasPermission("strategy_list-Edit")
    def update_notice(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        raw_ids = request.data.get("notice_type_ids") or []
        raw_users = request.data.get("notice_users") or []
        if not isinstance(raw_ids, list) or not isinstance(raw_users, list):
            raise BaseAppException("通知方式不正确")
        if "handlers" in request.data:
            raw_handlers = request.data.get("handlers")
            if not isinstance(raw_handlers, list):
                raise ValidationAppException("处理人不正确")
        else:
            raw_handlers = None
        try:
            notice_type_ids = [int(item) for item in raw_ids]
        except (TypeError, ValueError):
            raise BaseAppException("通知方式不正确")
        PolicyGroupService.update_notice(
            group,
            notice=bool(request.data.get("notice")),
            notice_type=str(request.data.get("notice_type") or ""),
            notice_type_ids=notice_type_ids,
            notice_users=raw_users,
            handlers=raw_handlers,
            operator=_operator(scope),
        )
        return WebUtils.response_success({"id": group.id})

    @action(methods=["post"], detail=False, url_path="update_enable")
    @HasPermission("strategy_list-Edit")
    def update_enable(self, request):
        scope = resolve_current_team_data_scope(request)
        group = _group_in_scope(scope, request.data.get("group_id"))
        enable = request.data.get("enable")
        if not isinstance(enable, bool):
            raise BaseAppException("请指定是否生效")
        PolicyGroupService.update_enable(group, enable=enable, operator=_operator(scope))
        log_operation(
            request,
            "update",
            "monitor",
            "策略组生效" if enable else "策略组停用",
            target_type="policy_group",
            target_id=group.id,
            detail={"group_id": group.id, "enable": enable},
        )
        return WebUtils.response_success({"id": group.id})

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
        group_id = group.id
        PolicyGroupService.delete_group(group, operator=_operator(scope))
        log_operation(
            request,
            "delete",
            "monitor",
            "删除策略组",
            target_type="policy_group",
            target_id=group_id,
            detail={"group_id": group_id},
        )
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
