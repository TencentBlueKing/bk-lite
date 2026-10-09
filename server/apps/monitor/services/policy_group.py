import copy

from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import (
    CollectConfig,
    Metric,
    MonitorAlert,
    MonitorInstanceOrganization,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupDefault,
    PolicyGroupMembership,
    PolicyGroupRule,
    PolicyInstanceBaseline,
    PolicyOrganization,
    PolicyTemplate,
)

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
from apps.monitor.services.policy import PolicyService


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
    def sync_coverage(group):
        member_ids = list(
            group.memberships.filter(state=PolicyGroupMembership.STATE_MEMBER).values_list("monitor_instance_id", flat=True)
        )
        for rule in group.rules.select_related("policy", "plugin"):
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
            push_alert_center=True,
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
        membership = PolicyGroupMembership.objects.filter(monitor_instance=instance, state=PolicyGroupMembership.STATE_MEMBER).select_related("policy_group").first()
        if membership is None or membership.policy_group_id is None:
            return membership
        group = membership.policy_group
        before = {rule.policy_id: set((rule.policy.source or {}).get("values") or []) for rule in group.rules.select_related("policy")}
        PolicyGroupService.sync_coverage(group)
        for rule in group.rules.select_related("policy"):
            after = set((rule.policy.source or {}).get("values") or [])
            if instance.id in before.get(rule.policy_id, set()) and instance.id not in after:
                PolicyGroupService._close_instance_alerts([rule.policy_id], instance.id, operator, "policy_group_member_left")
        return membership

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
        with transaction.atomic():
            pointer = PolicyGroupDefault.objects.select_for_update().filter(organization=organization, monitor_object=monitor_object).first()
            if pointer:
                return pointer.policy_group
            templates = list(
                PolicyTemplate.objects.filter(
                    template_type=PolicyTemplate.TYPE_BUILTIN,
                    monitor_object=monitor_object,
                ).select_related("plugin")
            )
            group = None
            if templates:
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
    def _has_legacy_policy(instance):
        policies = MonitorPolicy.objects.filter(monitor_object=instance.monitor_object, group_rule__isnull=True).only("source")
        for policy in policies:
            values = (policy.source or {}).get("values") or []
            if instance.id in values:
                return True
        return False

    @staticmethod
    def has_reported_baseline(policy, instance_id):
        return PolicyInstanceBaseline.objects.filter(policy_id=policy.id, monitor_instance_id=instance_id).exists()

    @staticmethod
    def update_rule(rule, *, threshold=None, notice_users=None, operator="system"):
        policy = rule.policy
        if threshold is not None:
            policy.threshold = threshold
        if notice_users is not None:
            policy.notice_users = notice_users
        policy.updated_by = operator
        policy.save(update_fields=["threshold", "notice_users", "updated_by", "updated_at"])
        alerts = list(MonitorAlert.objects.filter(policy_id=policy.id, status="new"))
        PolicyGroupService._publish_closed_alerts(alerts, [policy], operator, "policy_group_rule_changed")
        return rule

    @staticmethod
    def metric_id_for_policy(policy):
        query = policy.query_condition if isinstance(policy.query_condition, dict) else {}
        if query.get("type") == "formula":
            for item in query.get("queries") or []:
                if isinstance(item, dict) and item.get("metric_id"):
                    return item["metric_id"]
            return None
        return query.get("metric_id") or None

    @staticmethod
    def metric_names_for_policies(policies):
        ids = []
        for policy in policies:
            metric_id = PolicyGroupService.metric_id_for_policy(policy)
            if metric_id:
                ids.append(metric_id)
        if not ids:
            return {}
        return {row["id"]: row["name"] for row in Metric.objects.filter(id__in=ids).values("id", "name")}

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
                    push_alert_center=rule.push_alert_center,
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
        organizations = [organization] if organization is not None else list(
            MonitorInstanceOrganization.objects.filter(monitor_instance=instance).values_list("organization", flat=True)
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
        from apps.monitor.services.alert_lifecycle_notify import (
            NOTIFY_SCOPE_ALL_CONFIGURED,
            AlertLifecycleNotifier,
        )

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
