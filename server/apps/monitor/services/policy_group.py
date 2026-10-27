import copy
import json

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.core.exceptions.base_app_exception import BaseAppException, ValidationAppException
from apps.core.logger import monitor_logger as logger
from apps.monitor.constants.alert_policy import AlertConstants
from apps.monitor.models import (
    CollectConfig,
    Metric,
    MonitorAlert,
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorPlugin,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyGroupRule,
    PolicyInstanceBaseline,
    PolicyOrganization,
    PolicyTemplate,
)
from apps.monitor.services.policy import PolicyService
from apps.monitor.tasks.utils.policy_methods import period_to_seconds, source_has_dispatch_targets
from apps.monitor.tasks.utils.policy_multi import query_metric_items
from apps.monitor.utils.dimension import normalize_instance_identity

_POLICY_CLONE_FIELDS = (
    "alert_name",
    "collect_type",
    "query_condition",
    "schedule",
    "period",
    "group_algorithm",
    "algorithm",
    "group_by",
    "threshold",
    "trigger_count",
    "recovery_condition",
    "metric_unit",
    "calculation_unit",
    "threshold_unit",
    "compare_mode",
    "compare_value_kind",
    "compare_offset_hours",
    "compare_offset_days",
    "compare_baseline_weeks",
    "count_predicate",
    "forecast_target",
    "forecast_target_unit",
    "forecast_lookback",
    "recovery_threshold",
    "no_data_period",
    "no_data_level",
    "no_data_alert_name",
    "no_data_recovery_period",
    "notice",
    "notice_type",
    "notice_type_ids",
    "notice_users",
    "handlers",
    "enable",
    "enable_alerts",
)

_SCHEDULE_LIMITS = {"min": 59, "hour": 23, "day": 1}
_DURATION_TYPES = frozenset(_SCHEDULE_LIMITS)
_NO_DATA_LEVELS = frozenset({"critical", "error", "warning"})
_EMPTY_NO_DATA = {
    "enabled": False,
    "period": {},
    "level": "",
    "alert_name": "",
    "recovery_period": {},
}


def _json_equal(left, right):
    return json.dumps(left, sort_keys=True, default=str) == json.dumps(right, sort_keys=True, default=str)


def _editor_collect_type(rule, policy, value):
    """表单提交的是插件 id。同一插件保持原来的采集类型，换插件才改。"""
    text = "" if value is None else str(value).strip()
    if not text or text == str(policy.collect_type or ""):
        return policy.collect_type, None
    if not text.isdigit() or text == str(rule.plugin_id):
        return policy.collect_type if text == str(rule.plugin_id) else value, None
    plugin = MonitorPlugin.objects.filter(pk=int(text), monitor_object=policy.monitor_object_id).first()
    if plugin is None:
        raise ValidationAppException("采集插件无效")
    return plugin.collect_type or "", plugin


def _editor_query_condition(policy, value):
    """单指标回填会带上指标名。指标和筛选没变时保留原查询，避免被当成配方变更。"""
    if not isinstance(value, dict) or str(value.get("type") or "") != "metric":
        return value
    current = policy.query_condition if isinstance(policy.query_condition, dict) else {}
    same_metric = str(current.get("type") or "metric") == "metric" and str(current.get("metric_id") or "") == str(value.get("metric_id") or "")
    if same_metric and _json_equal(current.get("filter") or [], value.get("filter") or []):
        return current
    return {key: item for key, item in value.items() if key != "metric_name"}


def _keep_echoed_metric_unit(policy, payload):
    """指标没变、计算单位也没变时，不把目录单位写回空的 metric_unit。"""
    if "metric_unit" not in payload:
        return
    query = payload.get("query_condition", policy.query_condition)
    if "query_condition" in payload and not _json_equal(query, policy.query_condition):
        return
    for field in ("calculation_unit", "threshold_unit"):
        if field in payload and str(payload[field] or "") != str(getattr(policy, field) or ""):
            return
    payload["metric_unit"] = policy.metric_unit or ""


def _validation_text(exc):
    detail = getattr(exc, "detail", None)
    if isinstance(detail, list) and detail:
        return str(detail[0])
    if isinstance(detail, dict) and detail:
        first = next(iter(detail.values()))
        if isinstance(first, list) and first:
            return str(first[0])
        return str(first)
    return str(exc)


def _policy_group_by(rule):
    policy = getattr(rule, "policy", None)
    group_by = getattr(policy, "group_by", None) if policy is not None else None
    if not isinstance(group_by, list):
        return []
    return group_by


def no_data_carrier_rule_ids(rules):
    """按插件选出承载无数据告警的规则 id。

    同一插件优先取 group_by 恰为 ["instance_id"] 且 id 最小的规则；
    没有实例级规则时取该插件 id 最小的规则。
    """
    by_plugin = {}
    for rule in rules:
        by_plugin.setdefault(rule.plugin_id, []).append(rule)
    carrier_ids = set()
    for plugin_rules in by_plugin.values():
        instance_level = [rule for rule in plugin_rules if _policy_group_by(rule) == ["instance_id"]]
        pool = instance_level or plugin_rules
        carrier_ids.add(min(pool, key=lambda item: item.id).id)
    return carrier_ids


def _schedule_document(policy):
    schedule = getattr(policy, "schedule", None)
    if not isinstance(schedule, dict):
        return {}
    return copy.deepcopy(schedule)


def _no_data_document(policy):
    enable_alerts = getattr(policy, "enable_alerts", None) or []
    period = policy.no_data_period if isinstance(getattr(policy, "no_data_period", None), dict) else {}
    recovery = policy.no_data_recovery_period if isinstance(getattr(policy, "no_data_recovery_period", None), dict) else {}
    return {
        "enabled": AlertConstants.NO_DATA in enable_alerts,
        "period": copy.deepcopy(period),
        "level": policy.no_data_level or "",
        "alert_name": policy.no_data_alert_name or "",
        "recovery_period": copy.deepcopy(recovery),
    }


def group_detection_state(rules):
    """组级检测频率与无数据配置，以及两者是否在组内一致。"""
    ordered = sorted(rules, key=lambda rule: rule.id)
    if not ordered:
        return {
            "schedule": {},
            "schedule_uniform": True,
            "no_data": copy.deepcopy(_EMPTY_NO_DATA),
            "no_data_uniform": True,
        }
    schedules = [_schedule_document(rule.policy) for rule in ordered]
    schedule_uniform = all(_json_equal(item, schedules[0]) for item in schedules)
    carrier_ids = no_data_carrier_rule_ids(ordered)
    carriers = [rule for rule in ordered if rule.id in carrier_ids]
    carrier_docs = [_no_data_document(rule.policy) for rule in carriers]
    non_carrier_has_no_data = any(AlertConstants.NO_DATA in (rule.policy.enable_alerts or []) for rule in ordered if rule.id not in carrier_ids)
    no_data_uniform = bool(carrier_docs) and all(_json_equal(item, carrier_docs[0]) for item in carrier_docs)
    if non_carrier_has_no_data:
        no_data_uniform = False
    return {
        "schedule": copy.deepcopy(schedules[0]) if schedule_uniform else {},
        "schedule_uniform": schedule_uniform,
        "no_data": copy.deepcopy(carrier_docs[0]) if no_data_uniform else copy.deepcopy(_EMPTY_NO_DATA),
        "no_data_uniform": no_data_uniform,
    }


def _require_positive_int(value, message):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValidationAppException(message)
    return value


def _validate_duration(value, label, *, limit=False):
    if not isinstance(value, dict):
        raise ValidationAppException(f"{label}不正确")
    period_type = value.get("type")
    if period_type not in _DURATION_TYPES:
        raise ValidationAppException(f"{label}不正确")
    number = _require_positive_int(value.get("value"), f"{label}必须是正整数")
    if limit and number > _SCHEDULE_LIMITS[period_type]:
        raise ValidationAppException(f"{label}超出范围")
    return {"type": period_type, "value": number}


def _validate_schedule(schedule):
    return _validate_duration(schedule, "检测频率", limit=True)


def _validate_no_data(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        raise ValidationAppException("无数据告警格式不正确")
    if not payload["enabled"]:
        return {"enabled": False}
    period = _validate_duration(payload.get("period"), "无数据检测窗")
    recovery = _validate_duration(payload.get("recovery_period"), "无数据恢复窗")
    try:
        if period_to_seconds(period) < period_to_seconds(recovery):
            raise ValidationAppException("无数据检测窗不能小于恢复窗")
    except ValidationAppException:
        raise
    except BaseAppException as exc:
        raise ValidationAppException("无数据检测窗不正确") from exc
    level = payload.get("level")
    if level not in _NO_DATA_LEVELS:
        raise ValidationAppException("无数据告警级别不正确")
    name = payload.get("alert_name")
    max_length = MonitorPolicy._meta.get_field("no_data_alert_name").max_length
    if not isinstance(name, str) or not name.strip():
        raise ValidationAppException("请填写无数据告警名称")
    if len(name) > max_length:
        raise ValidationAppException("无数据告警名称过长")
    return {
        "enabled": True,
        "period": period,
        "level": level,
        "alert_name": name,
        "recovery_period": recovery,
    }


def _validate_alert_name(value):
    max_length = MonitorPolicy._meta.get_field("alert_name").max_length
    if not isinstance(value, str) or not value.strip():
        raise ValidationAppException("告警名称不能为空")
    if len(value) > max_length:
        raise ValidationAppException("告警名称过长")
    return value


def _validate_trigger_count(value):
    from rest_framework import serializers

    from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

    try:
        return MonitorPolicySerializer().validate_trigger_count(value)
    except serializers.ValidationError as exc:
        raise ValidationAppException(_validation_text(exc)) from exc


def _validate_recovery_condition(value):
    return _require_positive_int(value, "recovery_condition 必须是大于等于 1 的正整数")


def _validate_recovery_threshold(value):
    from rest_framework import serializers

    from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

    try:
        return MonitorPolicySerializer().validate_recovery_threshold(value)
    except serializers.ValidationError as exc:
        raise ValidationAppException(_validation_text(exc)) from exc


def _is_multi_policy(policy):
    query = policy.query_condition if isinstance(policy.query_condition, dict) else {}
    return query.get("type") == "multi"


def _enable_alerts_with_no_data(enable_alerts, enabled):
    current = [item for item in (enable_alerts or []) if item != AlertConstants.NO_DATA]
    if enabled:
        current.append(AlertConstants.NO_DATA)
    return current


class PolicyGroupService:
    """策略组成员决定的唯一写入入口。"""

    @staticmethod
    def create_from_templates(*, organization, monitor_object, name, templates, operator="system", origin=None):
        if not templates:
            raise BaseAppException("至少选择一条策略模板")
        with transaction.atomic():
            group = PolicyGroup.objects.create(
                organization=organization,
                monitor_object=monitor_object,
                name=name,
                origin=origin or PolicyGroup.ORIGIN_CUSTOM,
                created_by=operator,
                updated_by=operator,
            )
            for template in templates:
                if template.monitor_object_id != monitor_object.id:
                    raise BaseAppException("模板不属于该监控对象")
                PolicyGroupService._create_rule(group, template, operator)
            return group

    @staticmethod
    def join(*, instance, group, operator="system"):
        if instance.monitor_object_id != group.monitor_object_id:
            raise BaseAppException("实例与策略组的监控对象不一致")
        if not MonitorInstanceOrganization.objects.filter(
            monitor_instance=instance,
            organization=group.organization,
        ).exists():
            raise BaseAppException("实例不属于该策略组的组织")
        with transaction.atomic():
            membership = PolicyGroupMembership.objects.select_for_update().filter(monitor_instance=instance).first()
            if membership and membership.state == PolicyGroupMembership.STATE_MEMBER and membership.policy_group_id == group.id:
                return membership
            if membership and membership.state == PolicyGroupMembership.STATE_MEMBER and membership.policy_group_id:
                PolicyGroupService._detach(membership, operator)
                membership.refresh_from_db()
            if membership is None:
                membership = PolicyGroupMembership(monitor_instance=instance, created_by=operator)
            membership.policy_group = group
            membership.state = PolicyGroupMembership.STATE_MEMBER
            membership.updated_by = operator
            membership.save()
            PolicyGroupService.sync_coverage(group)
            return membership

    @staticmethod
    def leave(*, instance, operator="system"):
        with transaction.atomic():
            membership = PolicyGroupMembership.objects.select_for_update().filter(monitor_instance=instance).first()
            if membership is None:
                return PolicyGroupMembership.objects.create(
                    monitor_instance=instance,
                    state=PolicyGroupMembership.STATE_DECLINED,
                    created_by=operator,
                    updated_by=operator,
                )
            if membership.state == PolicyGroupMembership.STATE_MEMBER and membership.policy_group_id:
                PolicyGroupService._detach(membership, operator)
                membership.refresh_from_db()
            elif membership.state != PolicyGroupMembership.STATE_DECLINED:
                membership.state = PolicyGroupMembership.STATE_DECLINED
                membership.policy_group = None
                membership.updated_by = operator
                membership.save(update_fields=["state", "policy_group", "updated_by", "updated_at"])
            return membership

    @staticmethod
    def member_group_names(instance_ids, organization):
        """当前组织下，这些实例作为成员所在的策略组。未入组或不在本组织的不返回。"""
        if not instance_ids:
            return {}
        allowed = set(
            MonitorInstanceOrganization.objects.filter(
                monitor_instance_id__in=list(instance_ids),
                organization=organization,
            ).values_list("monitor_instance_id", flat=True)
        )
        if not allowed:
            return {}
        rows = PolicyGroupMembership.objects.filter(
            state=PolicyGroupMembership.STATE_MEMBER,
            monitor_instance_id__in=allowed,
            policy_group__organization=organization,
            policy_group__isnull=False,
        ).select_related("policy_group")
        return {row.monitor_instance_id: {"id": row.policy_group_id, "name": row.policy_group.name} for row in rows}

    @staticmethod
    def sync_coverage(group):
        member_ids = list(group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).values_list("monitor_instance_id", flat=True))
        for rule in group.rules.select_related("policy", "plugin"):
            previously_covered = bool((rule.policy.source or {}).get("values"))
            if member_ids:
                covered = list(
                    CollectConfig.objects.filter(
                        monitor_instance_id__in=member_ids,
                        monitor_plugin_id=rule.plugin_id,
                    )
                    .order_by("monitor_instance_id")
                    .values_list("monitor_instance_id", flat=True)
                    .distinct()
                )
            else:
                covered = []
            rule.policy.source = {"type": "instance", "values": covered}
            rule.policy.save(update_fields=["source", "updated_at"])
            PolicyGroupService._apply_scan_dispatch(rule.policy, previously_covered=previously_covered)

    @staticmethod
    def _create_rule(group, template, operator):
        recipe = PolicyService.recipe_fields_from_template(template)
        policy = MonitorPolicy.objects.create(
            monitor_object=group.monitor_object,
            name=template.name[:100],
            organizations=[group.organization],
            source={"type": "instance", "values": []},
            collect_type=template.plugin.collect_type or "",
            enable=True,
            notice=True,
            notice_users=[],
            handlers=[],
            source_template=None,
            created_by=operator,
            updated_by=operator,
            **recipe,
            schedule=PolicyService._default_duration((template.config or {}).get("schedule")),
        )
        PolicyOrganization.objects.create(policy=policy, organization=group.organization, created_by=operator, updated_by=operator)
        PolicyGroupService.ensure_scan_task(policy)
        return PolicyGroupRule.objects.create(
            group=group,
            plugin=template.plugin,
            source_template=template,
            policy=policy,
            name=template.name[:100],
            created_by=operator,
            updated_by=operator,
        )

    @staticmethod
    def _detach(membership, operator):
        group = membership.policy_group
        instance_id = membership.monitor_instance_id
        policy_ids = list(group.rules.values_list("policy_id", flat=True)) if group else []
        membership.policy_group = None
        membership.state = PolicyGroupMembership.STATE_DECLINED
        membership.updated_by = operator
        membership.save(update_fields=["policy_group", "state", "updated_by", "updated_at"])
        if group:
            PolicyGroupService.sync_coverage(group)
        PolicyGroupService._clear_instance_baselines(policy_ids, instance_id)
        PolicyGroupService._close_instance_alerts(policy_ids, instance_id, operator, "policy_group_member_left")

    @staticmethod
    def _close_instance_alerts(policy_ids, instance_id, operator, reason):
        if not policy_ids:
            return
        alerts = list(
            MonitorAlert.objects.filter(
                policy_id__in=policy_ids,
                monitor_instance_id=instance_id,
                status="new",
            )
        )
        policies = list(MonitorPolicy.objects.filter(id__in=policy_ids))
        PolicyGroupService._publish_closed_alerts(alerts, policies, operator, reason)

    @staticmethod
    def refresh_collect_coverage(instance, operator="system"):
        membership = (
            PolicyGroupMembership.objects.filter(monitor_instance=instance, state=PolicyGroupMembership.STATE_MEMBER)
            .select_related("policy_group")
            .first()
        )
        if membership is None or membership.policy_group_id is None:
            return membership
        group = membership.policy_group
        before = {rule.policy_id: set((rule.policy.source or {}).get("values") or []) for rule in group.rules.select_related("policy")}
        PolicyGroupService.sync_coverage(group)
        for rule in group.rules.select_related("policy"):
            after = set((rule.policy.source or {}).get("values") or [])
            if instance.id in before.get(rule.policy_id, set()) and instance.id not in after:
                PolicyGroupService._clear_instance_baselines([rule.policy_id], instance.id)
                PolicyGroupService._close_instance_alerts([rule.policy_id], instance.id, operator, "policy_group_member_left")
        return membership

    @staticmethod
    def _clear_instance_baselines(policy_ids, instance_id):
        """离开规则覆盖后丢掉该实例的无数据基准，重新加入要重新看到数据才建立。"""
        if not policy_ids or instance_id in (None, ""):
            return
        aliases = PolicyGroupService.instance_id_aliases(instance_id)
        if not aliases:
            return
        PolicyInstanceBaseline.objects.filter(policy_id__in=policy_ids, monitor_instance_id__in=aliases).delete()

    @staticmethod
    def apply_access_choice(instance, *, join, group_id=None, operator="system"):
        """只应由本次新建的实例调用。已有成员决定的实例不在这里处理。"""
        if PolicyGroupMembership.objects.filter(monitor_instance=instance).exists():
            return PolicyGroupMembership.objects.get(monitor_instance=instance)
        if not join:
            return PolicyGroupService.leave(instance=instance, operator=operator)
        group = PolicyGroup.objects.filter(id=group_id, monitor_object_id=instance.monitor_object_id).first()
        if group is None:
            raise BaseAppException("策略组不存在")
        return PolicyGroupService.join(instance=instance, group=group, operator=operator)

    @staticmethod
    def ensure_default(*, organization, monitor_object, operator="system"):
        """有指针就用它，包括用户删掉默认组后留下的空指针。没有内置模板时不写指针。"""
        pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object=monitor_object).first()
        if pointer:
            return pointer.policy_group
        templates = list(
            PolicyTemplate.objects.filter(
                template_type=PolicyTemplate.TYPE_BUILTIN,
                monitor_object=monitor_object,
            ).select_related("plugin")
        )
        if not templates:
            return None
        try:
            with transaction.atomic():
                pointer = PolicyGroupDefault.objects.select_for_update().filter(organization=organization, monitor_object=monitor_object).first()
                if pointer:
                    return pointer.policy_group
                group = PolicyGroupService.create_from_templates(
                    organization=organization,
                    monitor_object=monitor_object,
                    name=f"{monitor_object.name}默认告警",
                    templates=templates,
                    operator=operator,
                    origin=PolicyGroup.ORIGIN_SYSTEM,
                )
                PolicyGroupDefault.objects.create(
                    organization=organization,
                    monitor_object=monitor_object,
                    policy_group=group,
                    created_by=operator,
                    updated_by=operator,
                )
                return group
        except IntegrityError:
            pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object=monitor_object).first()
            return pointer.policy_group if pointer else None

    @staticmethod
    def join_failure_reason(exc):
        if isinstance(exc, BaseAppException) and exc.message:
            return str(exc.message)[:80]
        return "策略组加入失败，可在实例页重新加入"

    @staticmethod
    def remember_join_failure(instance, operator="system"):
        """记下加入失败，方便实例页区分「没选过」和「选了没加上」。写入失败只记日志。"""
        try:
            with transaction.atomic():
                membership = PolicyGroupMembership.objects.select_for_update().filter(monitor_instance=instance).first()
                if membership and membership.state == PolicyGroupMembership.STATE_MEMBER:
                    return membership
                if membership is None:
                    membership = PolicyGroupMembership(monitor_instance=instance, created_by=operator)
                membership.state = PolicyGroupMembership.STATE_FAILED
                membership.policy_group = None
                membership.updated_by = operator
                membership.save()
                return membership
        except Exception as exc:
            logger.exception(
                "event=policy_group_failure_record_failed instance_id=%s failed_stage=record_failure error_type=%s",
                instance.id,
                type(exc).__name__,
            )
            return None

    @staticmethod
    def _outcome(instance_id, membership):
        if membership is None:
            return {"instance_id": instance_id, "outcome": "failed", "reason": "策略组加入失败，可在实例页重新加入"}
        state = membership.state
        if state == PolicyGroupMembership.STATE_MEMBER:
            group = membership.policy_group
            return {
                "instance_id": instance_id,
                "outcome": "joined",
                "group_id": membership.policy_group_id,
                "group_name": group.name if group else "",
            }
        if state == PolicyGroupMembership.STATE_DECLINED:
            return {"instance_id": instance_id, "outcome": "declined", "reason": "已关闭加入"}
        if state == PolicyGroupMembership.STATE_SKIPPED:
            return {"instance_id": instance_id, "outcome": "skipped", "reason": "未入组"}
        if state == PolicyGroupMembership.STATE_FAILED:
            return {"instance_id": instance_id, "outcome": "failed", "reason": "策略组加入失败，可在实例页重新加入"}
        return {"instance_id": instance_id, "outcome": state or "failed", "reason": "策略组加入失败，可在实例页重新加入"}

    @staticmethod
    def apply_best_effort_auto_join(instance, organization_ids, operator="system"):
        """自动加入失败不向外抛。失败记成可在实例页看到的加入失败，不回滚实例。"""
        try:
            with transaction.atomic():
                return PolicyGroupService.consider_auto_join(instance, organization_ids, operator=operator)
        except Exception as exc:
            logger.exception(
                "event=policy_group_auto_join_failed instance_id=%s failed_stage=auto_join error_type=%s",
                instance.id,
                type(exc).__name__,
            )
            return PolicyGroupService.remember_join_failure(instance, operator)

    @staticmethod
    def apply_onboarding_memberships(*, new_instances, existing_instances, created_ids, choice, operator="system"):
        """接入事务提交后再写策略组。单条失败只记日志和实例上的失败状态，不中断其余实例。"""
        explicit_choice = isinstance(choice, dict) and "join" in choice
        results = []
        for raw in new_instances or []:
            instance_id = raw.get("instance_id")
            if instance_id not in created_ids:
                continue
            instance = MonitorInstance.objects.filter(id=instance_id).first()
            if instance is None:
                results.append({"instance_id": instance_id, "outcome": "failed", "reason": "实例不存在"})
                continue
            existing = PolicyGroupMembership.objects.filter(monitor_instance=instance).first()
            if existing is not None:
                results.append(PolicyGroupService._outcome(instance_id, existing))
                continue
            try:
                with transaction.atomic():
                    if explicit_choice:
                        membership = PolicyGroupService.apply_access_choice(
                            instance,
                            join=bool(choice.get("join")),
                            group_id=choice.get("group_id"),
                            operator=operator,
                        )
                    else:
                        membership = PolicyGroupService.consider_auto_join(instance, raw.get("group_ids") or [], operator=operator)
                results.append(PolicyGroupService._outcome(instance_id, membership))
            except Exception as exc:
                logger.exception(
                    "event=policy_group_onboarding_failed instance_id=%s failed_stage=onboarding_join error_type=%s",
                    instance_id,
                    type(exc).__name__,
                )
                PolicyGroupService.remember_join_failure(instance, operator)
                results.append({"instance_id": instance_id, "outcome": "failed", "reason": PolicyGroupService.join_failure_reason(exc)})
        for raw in existing_instances or []:
            instance = MonitorInstance.objects.filter(id=raw.get("instance_id")).first()
            if instance is None:
                continue
            try:
                with transaction.atomic():
                    PolicyGroupService.refresh_collect_coverage(instance, operator=operator)
                results.append({"instance_id": instance.id, "outcome": "refreshed", "reason": "已接入实例保持原策略组"})
            except Exception as exc:
                logger.exception(
                    "event=policy_group_coverage_refresh_failed instance_id=%s failed_stage=refresh_coverage error_type=%s",
                    instance.id,
                    type(exc).__name__,
                )
                results.append({"instance_id": instance.id, "outcome": "refresh_failed", "reason": "策略组覆盖未刷新，可在实例页重新加入"})
        return results

    @staticmethod
    def consider_auto_join(instance, organization_ids, operator="system"):
        if PolicyGroupMembership.objects.filter(monitor_instance=instance).exists():
            return PolicyGroupMembership.objects.get(monitor_instance=instance)
        org_ids = []
        for raw in organization_ids or []:
            if raw in (None, ""):
                continue
            org_ids.append(int(raw))
        if PolicyGroupService._has_legacy_policy(instance) or len(org_ids) != 1:
            return PolicyGroupService._mark(instance, PolicyGroupMembership.STATE_SKIPPED, operator)
        group = PolicyGroupService.ensure_default(organization=org_ids[0], monitor_object=instance.monitor_object, operator=operator)
        if group is None:
            return PolicyGroupService._mark(instance, PolicyGroupMembership.STATE_SKIPPED, operator)
        return PolicyGroupService.join(instance=instance, group=group, operator=operator)

    @staticmethod
    def _mark(instance, state, operator):
        membership, _ = PolicyGroupMembership.objects.get_or_create(
            monitor_instance=instance,
            defaults={"state": state, "created_by": operator, "updated_by": operator},
        )
        if membership.state != state or membership.policy_group_id:
            membership.state = state
            membership.policy_group = None
            membership.updated_by = operator
            membership.save(update_fields=["state", "policy_group", "updated_by", "updated_at"])
        return membership

    @staticmethod
    def instance_id_aliases(instance_id):
        if instance_id in (None, ""):
            return set()
        aliases = {str(instance_id)}
        try:
            identity = normalize_instance_identity(instance_id)
        except ValueError:
            return aliases
        for key in ("storage_instance_key", "logical_instance_value"):
            value = identity.get(key)
            if value not in (None, ""):
                aliases.add(str(value))
        return aliases

    @staticmethod
    def source_covers_instance(source_values, instance_id):
        aliases = PolicyGroupService.instance_id_aliases(instance_id)
        if not aliases:
            return False
        for value in source_values or []:
            if PolicyGroupService.instance_id_aliases(value) & aliases:
                return True
        return False

    @staticmethod
    def _has_legacy_policy(instance):
        policies = MonitorPolicy.objects.filter(monitor_object=instance.monitor_object, group_rule__isnull=True).only("source")
        for policy in policies:
            values = (policy.source or {}).get("values") or []
            if PolicyGroupService.source_covers_instance(values, instance.id):
                return True
        return False

    @staticmethod
    def legacy_policies(instance):
        found = []
        policies = MonitorPolicy.objects.filter(monitor_object_id=instance.monitor_object_id, group_rule__isnull=True).only(
            "id", "name", "enable", "source"
        )
        for policy in policies:
            values = (policy.source or {}).get("values") or []
            if PolicyGroupService.source_covers_instance(values, instance.id):
                found.append({"id": policy.id, "name": policy.name, "enable": policy.enable})
        return found

    @staticmethod
    def open_alert_counts(policy_ids):
        if not policy_ids:
            return {}
        rows = MonitorAlert.objects.filter(policy_id__in=list(policy_ids), status="new").values("policy_id").annotate(total=Count("id"))
        return {row["policy_id"]: row["total"] for row in rows}

    @staticmethod
    def retire_policies_for_plugins(plugin_ids, operator="system"):
        """插件删除前收掉组内规则对应的策略，避免规则行消失后策略还在扫描。"""
        rules = list(PolicyGroupRule.objects.filter(plugin_id__in=list(plugin_ids)).select_related("policy"))
        for rule in rules:
            policy = rule.policy
            if policy is not None and MonitorPolicy.objects.filter(id=policy.id).exists():
                PolicyGroupService._retire_policy(policy, operator)

    @staticmethod
    def has_reported_baseline(policy, instance_id):
        return PolicyInstanceBaseline.objects.filter(policy_id=policy.id, monitor_instance_id=instance_id).exists()

    @staticmethod
    def update_rule(
        rule,
        *,
        threshold=None,
        condition_thresholds=None,
        trigger_count=None,
        recovery_condition=None,
        recovery_threshold=None,
        alert_name=None,
        operator="system",
    ):
        # select_for_update 关闭告警必须在事务里。请求本身不包事务，写在保存之后会留下已改规则、告警仍未恢复。
        with transaction.atomic():
            locked = MonitorPolicy.objects.select_for_update().get(pk=rule.policy_id)
            rule.policy = locked
            return PolicyGroupService._update_rule_locked(
                rule,
                threshold=threshold,
                condition_thresholds=condition_thresholds,
                trigger_count=trigger_count,
                recovery_condition=recovery_condition,
                recovery_threshold=recovery_threshold,
                alert_name=alert_name,
                operator=operator,
            )

    @staticmethod
    def _update_rule_locked(
        rule,
        *,
        threshold=None,
        condition_thresholds=None,
        trigger_count=None,
        recovery_condition=None,
        recovery_threshold=None,
        alert_name=None,
        operator="system",
    ):
        policy = rule.policy
        update_fields = ["updated_by", "updated_at"]
        closes_alerts = False
        if condition_thresholds is not None:
            before = copy.deepcopy(policy.query_condition)
            PolicyGroupService._replace_condition_thresholds(policy, condition_thresholds)
            update_fields.append("query_condition")
            if not _json_equal(before, policy.query_condition):
                closes_alerts = True
        elif threshold is not None:
            if not _json_equal(policy.threshold, threshold):
                closes_alerts = True
            policy.threshold = copy.deepcopy(threshold)
            update_fields.append("threshold")
        if trigger_count is not None:
            trigger_count = _validate_trigger_count(trigger_count)
            if policy.trigger_count != trigger_count:
                closes_alerts = True
            policy.trigger_count = trigger_count
            update_fields.append("trigger_count")
        if recovery_condition is not None:
            recovery_condition = _validate_recovery_condition(recovery_condition)
            if policy.recovery_condition != recovery_condition:
                closes_alerts = True
            policy.recovery_condition = recovery_condition
            update_fields.append("recovery_condition")
        if recovery_threshold is not None:
            if _is_multi_policy(policy):
                raise ValidationAppException("多指标条件不支持恢复阈值")
            cleaned = _validate_recovery_threshold(recovery_threshold) or {}
            if not _json_equal(policy.recovery_threshold or {}, cleaned):
                closes_alerts = True
            policy.recovery_threshold = copy.deepcopy(cleaned)
            update_fields.append("recovery_threshold")
        if alert_name is not None:
            policy.alert_name = _validate_alert_name(alert_name)
            update_fields.append("alert_name")
        policy.updated_by = operator
        policy.save(update_fields=update_fields)
        if closes_alerts:
            alerts = list(MonitorAlert.objects.filter(policy_id=policy.id, status="new"))
            PolicyGroupService._publish_closed_alerts(alerts, [policy], operator, "policy_group_rule_changed")
        return rule

    _RULE_EDITOR_FIELDS = (
        "alert_name",
        "collect_type",
        "query_condition",
        "period",
        "group_algorithm",
        "algorithm",
        "group_by",
        "threshold",
        "trigger_count",
        "recovery_condition",
        "metric_unit",
        "calculation_unit",
        "threshold_unit",
        "compare_mode",
        "compare_value_kind",
        "compare_offset_hours",
        "compare_offset_days",
        "compare_baseline_weeks",
        "count_predicate",
        "forecast_target",
        "forecast_target_unit",
        "forecast_lookback",
        "recovery_threshold",
    )
    _RULE_EDITOR_CLOSE_FIELDS = tuple(field for field in _RULE_EDITOR_FIELDS if field != "alert_name")

    @staticmethod
    def apply_rule_editor(rule, payload, operator="system"):
        """写入这条规则自己的名称、指标和告警条件。组织、实例范围、频率、无数据和通知保持原值。"""
        if not isinstance(payload, dict):
            raise ValidationAppException("规则内容无效")
        with transaction.atomic():
            locked = MonitorPolicy.objects.select_for_update().get(pk=rule.policy_id)
            rule.policy = locked
            policy = locked
            closes_alerts = False
            update_fields = ["updated_by", "updated_at"]
            prepared = dict(payload)
            plugin = None
            if "collect_type" in prepared:
                prepared["collect_type"], plugin = _editor_collect_type(rule, policy, prepared.get("collect_type"))
            if isinstance(prepared.get("query_condition"), dict):
                prepared["query_condition"] = _editor_query_condition(policy, prepared["query_condition"])
            _keep_echoed_metric_unit(policy, prepared)
            query = prepared.get("query_condition")
            if not isinstance(query, dict):
                query = policy.query_condition if isinstance(policy.query_condition, dict) else {}
            for field in PolicyGroupService._RULE_EDITOR_FIELDS:
                if field not in prepared:
                    continue
                if field == "recovery_threshold" and (query.get("type") == "multi" or _is_multi_policy(policy)):
                    continue
                value = prepared[field]
                if field == "alert_name":
                    value = _validate_alert_name(value)
                elif field == "trigger_count":
                    value = _validate_trigger_count(value)
                elif field == "recovery_condition":
                    value = _validate_recovery_condition(value)
                elif field == "recovery_threshold":
                    value = _validate_recovery_threshold(value) or {}
                current = getattr(policy, field)
                if field in PolicyGroupService._RULE_EDITOR_CLOSE_FIELDS and not _json_equal(current, value):
                    closes_alerts = True
                setattr(policy, field, copy.deepcopy(value) if isinstance(value, (dict, list)) else value)
                update_fields.append(field)
            rule_fields = []
            if plugin is not None:
                closes_alerts = True
                rule.plugin = plugin
                rule_fields.append("plugin")
                previously_covered = bool((policy.source or {}).get("values"))
                member_ids = list(
                    rule.group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).values_list("monitor_instance_id", flat=True)
                )
                if member_ids:
                    covered = list(
                        CollectConfig.objects.filter(monitor_instance_id__in=member_ids, monitor_plugin_id=plugin.id)
                        .order_by("monitor_instance_id")
                        .values_list("monitor_instance_id", flat=True)
                        .distinct()
                    )
                else:
                    covered = []
                policy.source = {"type": "instance", "values": covered}
                update_fields.append("source")
                PolicyGroupService._apply_scan_dispatch(policy, previously_covered=previously_covered)
            if "name" in prepared:
                name = str(prepared.get("name") or "").strip()
                if not name:
                    raise ValidationAppException("请填写规则名称")
                if len(name) > 100:
                    raise ValidationAppException("规则名称过长")
                rule.name = name
                rule_fields.append("name")
                policy.name = name
                update_fields.append("name")
            if rule_fields:
                rule.updated_by = operator
                rule.save(update_fields=[*dict.fromkeys(rule_fields), "updated_by", "updated_at"])
            policy.updated_by = operator
            policy.save(update_fields=list(dict.fromkeys(update_fields)))
            if closes_alerts:
                alerts = list(MonitorAlert.objects.filter(policy_id=policy.id, status="new"))
                PolicyGroupService._publish_closed_alerts(alerts, [policy], operator, "policy_group_rule_changed")
            return closes_alerts

    @staticmethod
    def update_detection(group, *, schedule=None, no_data=None, operator="system"):
        """把检测频率写到组内每条策略，把无数据告警写到每个插件的承载规则。"""
        if schedule is None and no_data is None:
            raise ValidationAppException("请至少设置检测频率或无数据告警")
        validated_schedule = _validate_schedule(schedule) if schedule is not None else None
        validated_no_data = _validate_no_data(no_data) if no_data is not None else None
        with transaction.atomic():
            rules = list(PolicyGroupRule.objects.select_for_update().filter(group=group).order_by("id"))
            locked_policies = {
                policy.id: policy
                for policy in MonitorPolicy.objects.select_for_update().filter(id__in=[rule.policy_id for rule in rules]).order_by("id")
            }
            for rule in rules:
                rule.policy = locked_policies[rule.policy_id]
            if validated_schedule is not None:
                PolicyGroupService._apply_group_schedule(rules, validated_schedule, operator)
            if validated_no_data is not None:
                PolicyGroupService._apply_group_no_data(rules, validated_no_data, operator)
        return group

    @staticmethod
    def _apply_group_schedule(rules, schedule, operator):
        from django_celery_beat.models import PeriodicTask

        from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

        now = timezone.now()
        for rule in rules:
            policy = rule.policy
            policy.schedule = copy.deepcopy(schedule)
            policy.updated_by = operator
            policy.updated_at = now
            policy.save(update_fields=["schedule", "updated_by", "updated_at"])
            MonitorPolicyViewSet().update_or_create_task(policy.id, policy.schedule)
            if not policy.enable or not source_has_dispatch_targets(policy.source):
                PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").update(enabled=False)

    @staticmethod
    def _apply_group_no_data(rules, no_data, operator):
        from apps.monitor.services.policy_baseline import PolicyBaselineService

        carrier_ids = no_data_carrier_rule_ids(rules)
        now = timezone.now()
        for rule in rules:
            policy = rule.policy
            was_enabled = AlertConstants.NO_DATA in (policy.enable_alerts or [])
            should_enable = bool(no_data["enabled"]) and rule.id in carrier_ids
            policy.enable_alerts = _enable_alerts_with_no_data(policy.enable_alerts, should_enable)
            policy.updated_by = operator
            policy.updated_at = now
            update_fields = ["enable_alerts", "updated_by", "updated_at"]
            if should_enable:
                policy.no_data_period = copy.deepcopy(no_data["period"])
                policy.no_data_level = no_data["level"]
                policy.no_data_alert_name = no_data["alert_name"]
                policy.no_data_recovery_period = copy.deepcopy(no_data["recovery_period"])
                update_fields.extend(["no_data_period", "no_data_level", "no_data_alert_name", "no_data_recovery_period"])
            elif rule.id in carrier_ids:
                policy.no_data_period = {}
                policy.no_data_level = ""
                policy.no_data_alert_name = ""
                policy.no_data_recovery_period = {}
                update_fields.extend(["no_data_period", "no_data_level", "no_data_alert_name", "no_data_recovery_period"])
            policy.save(update_fields=update_fields)
            if should_enable and not was_enabled:
                PolicyBaselineService(policy).refresh()
            elif was_enabled and not should_enable:
                alerts = list(MonitorAlert.objects.filter(policy_id=policy.id, alert_type=AlertConstants.NO_DATA, status="new"))
                PolicyGroupService._publish_closed_alerts(alerts, [policy], operator, "no_data_disabled")
                PolicyBaselineService(policy).clear()

    @staticmethod
    def _replace_condition_thresholds(policy, condition_thresholds):
        from apps.monitor.expression.errors import FormulaError
        from apps.monitor.expression.validators import validate_multi_condition
        from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

        query = policy.query_condition if isinstance(policy.query_condition, dict) else {}
        if query.get("type") != "multi":
            raise ValidationAppException("只有多指标条件可以按条件改阈值")
        if not isinstance(condition_thresholds, dict):
            raise ValidationAppException("条件阈值格式不正确")
        queries = [item for item in query.get("queries") or [] if isinstance(item, dict)]
        refs = [str(item.get("ref") or "") for item in queries]
        if set(condition_thresholds) != set(refs) or any(not ref for ref in refs):
            raise ValidationAppException("条件阈值与条件不对应")
        replaced = copy.deepcopy(query)
        for item in replaced.get("queries") or []:
            item["threshold"] = condition_thresholds[item.get("ref")]
        try:
            validate_multi_condition(replaced)
        except FormulaError as exc:
            raise ValidationAppException(str(exc)) from exc
        errors = {}
        MonitorPolicySerializer()._validate_multi_condition_metrics(replaced, errors)
        if errors:
            raise ValidationAppException(str(errors.get("query_condition") or "多指标条件不合法"))
        policy.query_condition = replaced

    @staticmethod
    def update_notice(
        group,
        *,
        notice,
        notice_type="",
        notice_type_ids=None,
        notice_users=None,
        handlers=None,
        operator="system",
    ):
        """把同一套通知写到组内每条策略上。传入处理人时一并写入，不改已有告警。"""
        enabled = bool(notice)
        channel_ids = [] if not enabled else [int(item) for item in (notice_type_ids or [])]
        users = [] if not enabled else [str(item) for item in (notice_users or []) if str(item) != ""]
        if enabled and not channel_ids:
            raise BaseAppException("请选择通知方式")
        resolved_handlers = None
        if handlers is not None:
            resolved_handlers = PolicyGroupService._handlers_for_group(group, handlers)
        fields = {
            "notice": enabled,
            "notice_type": "" if not enabled else (notice_type or "")[:50],
            "notice_type_ids": channel_ids,
            "notice_users": users,
            "updated_by": operator,
            "updated_at": timezone.now(),
        }
        if resolved_handlers is not None:
            fields["handlers"] = resolved_handlers
        with transaction.atomic():
            MonitorPolicy.objects.filter(group_rule__group=group).update(**fields)
        return group

    @staticmethod
    def _handlers_for_group(group, handlers):
        from apps.monitor.services.alert_handlers import AlertHandlerInvalid, normalize_policy_handlers

        if not isinstance(handlers, list):
            raise ValidationAppException("处理人不正确")
        try:
            return normalize_policy_handlers(handlers, [group.organization])
        except AlertHandlerInvalid as exc:
            raise ValidationAppException(str(exc)) from exc

    @staticmethod
    def update_enable(group, *, enable, operator="system"):
        """整组生效或停用。停用结束未恢复告警并停止扫描；再次生效从当前时间继续扫，不补历史告警。成员不变。"""
        from django_celery_beat.models import PeriodicTask

        enabled = bool(enable)
        now = timezone.now()
        with transaction.atomic():
            policies = list(MonitorPolicy.objects.select_for_update().filter(group_rule__group=group))
            changing = [policy for policy in policies if bool(policy.enable) != enabled]
            if not changing:
                return group
            ids = [policy.id for policy in changing]
            fields = {"enable": enabled, "updated_by": operator, "updated_at": now}
            if enabled:
                fields["last_run_time"] = now
            MonitorPolicy.objects.filter(id__in=ids).update(**fields)
            if not enabled:
                alerts = list(MonitorAlert.objects.filter(policy_id__in=ids, status="new"))
                PolicyGroupService._publish_closed_alerts(alerts, changing, operator, "policy_disabled")
            for policy in changing:
                covered = source_has_dispatch_targets(policy.source)
                PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").update(enabled=enabled and covered)
        return group

    @staticmethod
    def metric_ids_for_policy(policy):
        query = policy.query_condition if isinstance(policy.query_condition, dict) else {}
        return [item.get("metric_id") for item in query_metric_items(query) if isinstance(item, dict) and item.get("metric_id")]

    @staticmethod
    def metric_id_for_policy(policy):
        ids = PolicyGroupService.metric_ids_for_policy(policy)
        return ids[0] if ids else None

    @staticmethod
    def metric_names_for_policies(policies):
        ids = []
        for policy in policies:
            ids.extend(PolicyGroupService.metric_ids_for_policy(policy))
        if not ids:
            return {}
        return {row["id"]: row["name"] for row in Metric.objects.filter(id__in=ids).values("id", "name")}

    @staticmethod
    def filter_rules_for_access(rules, *, plugin_id=None, collect_type=None):
        """接入页只展示当前插件的规则；不传筛选时返回全部，供策略组管理页使用。"""
        items = list(rules)
        if plugin_id is not None:
            return [rule for rule in items if rule.plugin_id == plugin_id]
        wanted = str(collect_type or "").strip()
        if not wanted:
            return items
        matched = []
        for rule in items:
            plugin = getattr(rule, "plugin", None)
            policy = getattr(rule, "policy", None)
            plugin_collect = str(getattr(plugin, "collect_type", "") or "").strip()
            policy_collect = str(getattr(policy, "collect_type", "") or "").strip()
            if wanted in {plugin_collect, policy_collect}:
                matched.append(rule)
        return matched

    @staticmethod
    def copy_group(group, *, name, operator="system"):
        """按当前组内策略整份复制。模板后来的修改，以及模板是否还在，都不参与这次复制。"""
        rules = list(group.rules.select_related("plugin", "source_template", "policy").order_by("id"))
        with transaction.atomic():
            copied = PolicyGroup.objects.create(
                organization=group.organization,
                monitor_object=group.monitor_object,
                name=name,
                origin=PolicyGroup.ORIGIN_CUSTOM,
                created_by=operator,
                updated_by=operator,
            )
            for rule in rules:
                policy = PolicyGroupService._clone_policy(copied, rule.policy, operator)
                PolicyGroupRule.objects.create(
                    group=copied,
                    plugin=rule.plugin,
                    source_template=rule.source_template,
                    policy=policy,
                    name=rule.name,
                    created_by=operator,
                    updated_by=operator,
                )
            return copied

    @staticmethod
    def _clone_policy(group, source_policy, operator):
        fields = {}
        for field in _POLICY_CLONE_FIELDS:
            value = getattr(source_policy, field)
            if isinstance(value, (dict, list)):
                value = copy.deepcopy(value)
            fields[field] = value
        policy = MonitorPolicy.objects.create(
            monitor_object=group.monitor_object,
            name=(source_policy.name or "")[:100],
            organizations=[group.organization],
            source={"type": "instance", "values": []},
            source_template=None,
            created_by=operator,
            updated_by=operator,
            **fields,
        )
        PolicyOrganization.objects.create(
            policy=policy,
            organization=group.organization,
            created_by=operator,
            updated_by=operator,
        )
        PolicyGroupService.ensure_scan_task(policy)
        return policy

    @staticmethod
    def save_rule_as_template(rule, *, operator="system"):
        policy = rule.policy
        user = type("User", (), {"username": operator, "domain": "domain.com"})()
        return PolicyService.create_custom_template(
            organization=rule.group.organization,
            monitor_object_id=rule.group.monitor_object_id,
            plugin_id=rule.plugin_id,
            name=rule.name,
            description="",
            config={"metric_name": "cpu_usage_total", "threshold": policy.threshold},
            user=user,
        )

    @staticmethod
    def set_default(group, operator="system"):
        pointer, _ = PolicyGroupDefault.objects.get_or_create(
            organization=group.organization,
            monitor_object=group.monitor_object,
            defaults={"policy_group": group, "created_by": operator, "updated_by": operator},
        )
        pointer.policy_group = group
        pointer.updated_by = operator
        pointer.save(update_fields=["policy_group", "updated_by", "updated_at"])
        return pointer

    @staticmethod
    def create_standalone(*, instance, template, operator="system", organization=None):
        recipe = PolicyService.recipe_fields_from_template(template)
        organizations = (
            [organization]
            if organization is not None
            else list(MonitorInstanceOrganization.objects.filter(monitor_instance=instance).values_list("organization", flat=True))
        )
        policy = MonitorPolicy.objects.create(
            monitor_object=instance.monitor_object,
            name=template.name[:100],
            organizations=organizations,
            source={"type": "instance", "values": [instance.id]},
            enable=True,
            notice=True,
            notice_users=[],
            handlers=[],
            source_template=None,
            created_by=operator,
            updated_by=operator,
            **recipe,
            schedule=PolicyService._default_duration((template.config or {}).get("schedule")),
        )
        for org in organizations:
            PolicyOrganization.objects.create(policy=policy, organization=org, created_by=operator, updated_by=operator)
        PolicyGroupService.ensure_scan_task(policy)
        return policy

    @staticmethod
    def delete_group(group, operator="system"):
        with transaction.atomic():
            policies = [rule.policy for rule in group.rules.select_related("policy")]
            for membership in list(group.memberships.select_for_update()):
                if membership.state == PolicyGroupMembership.STATE_MEMBER:
                    PolicyGroupService._detach(membership, operator)
            for policy in policies:
                if MonitorPolicy.objects.filter(id=policy.id).exists():
                    PolicyGroupService._retire_policy(policy, operator)
            PolicyGroupDefault.objects.filter(policy_group=group).update(policy_group=None, updated_by=operator)
            group.delete()

    @staticmethod
    def ensure_scan_task(policy):
        """组内规则和单独规则都是真实策略，没有扫描任务就不会告警。"""
        from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

        schedule = PolicyService._default_duration(policy.schedule)
        if policy.schedule != schedule:
            policy.schedule = schedule
            policy.save(update_fields=["schedule", "updated_at"])
        from django_celery_beat.models import PeriodicTask

        if PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").exists():
            return
        MonitorPolicyViewSet().update_or_create_task(policy.id, schedule)
        if not source_has_dispatch_targets(policy.source):
            PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").update(enabled=False)

    @staticmethod
    def _apply_scan_dispatch(policy, *, previously_covered):
        """没有可扫描实例时停掉 Beat 派发。覆盖从空变为有实例时，从当前时间开始扫。"""
        from django_celery_beat.models import PeriodicTask

        task_name = f"scan_policy_task_{policy.id}"
        if not policy.enable or not source_has_dispatch_targets(policy.source):
            PeriodicTask.objects.filter(name=task_name).update(enabled=False)
            return
        if not previously_covered:
            MonitorPolicy.objects.filter(id=policy.id).update(last_run_time=timezone.now())
        PeriodicTask.objects.filter(name=task_name).update(enabled=True)

    @staticmethod
    def repair_empty_scan_settings():
        """补上组规则创建时漏写的检测周期和阈值开关，已有值保持不变。"""
        default_period = PolicyService._default_duration(None)
        updated = 0
        for rule in PolicyGroupRule.objects.select_related("policy").iterator():
            policy = rule.policy
            fields = []
            if not policy.period:
                policy.period = copy.deepcopy(default_period)
                fields.append("period")
            if not policy.enable_alerts:
                policy.enable_alerts = ["threshold"]
                fields.append("enable_alerts")
            if not fields:
                continue
            policy.save(update_fields=[*fields, "updated_at"])
            updated += 1
        return updated

    @staticmethod
    def _retire_policy(policy, operator):
        """组内规则对应的是一条真实策略，删除时和策略列表删除走同一套清理。"""
        from django_celery_beat.models import PeriodicTask

        from apps.monitor.services.policy_baseline import PolicyBaselineService

        PolicyBaselineService(policy).clear()
        alerts = list(MonitorAlert.objects.filter(policy_id=policy.id, status="new"))
        PolicyGroupService._publish_closed_alerts(alerts, [policy], operator, "policy_deleted")
        PeriodicTask.objects.filter(name=f"scan_policy_task_{policy.id}").delete()
        PolicyOrganization.objects.filter(policy_id=policy.id).delete()
        policy.delete()

    @staticmethod
    def _publish_closed_alerts(alerts, policies, operator, reason):
        if not alerts:
            return
        PolicyService._mark_new_alerts_closed(alerts, operator, reason)
        from apps.monitor.services.alert_lifecycle_notify import NOTIFY_SCOPE_ALL_CONFIGURED, AlertLifecycleNotifier

        notifier = AlertLifecycleNotifier(policies_by_id={policy.id: policy for policy in policies if policy is not None})
        notifier.enqueue_alert_center_deliveries(alerts, "closed", operator=operator, reason=reason)
        closed = tuple(alerts)
        transaction.on_commit(
            lambda: notifier.notify_alerts(
                closed,
                action="closed",
                operator=operator,
                reason=reason,
                notify_scope=NOTIFY_SCOPE_ALL_CONFIGURED,
            )
        )
