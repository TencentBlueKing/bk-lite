from django.db import transaction

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import (
    CollectConfig,
    MonitorAlert,
    MonitorInstanceOrganization,
    MonitorPolicy,
    PolicyGroup,
    PolicyGroupMembership,
    PolicyGroupRule,
    PolicyInstanceBaseline,
    PolicyOrganization,
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
        )
        PolicyOrganization.objects.create(policy=policy, organization=group.organization, created_by=operator, updated_by=operator)
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
        PolicyGroupService._close_instance_alerts(policy_ids, instance_id, operator)

    @staticmethod
    def _close_instance_alerts(policy_ids, instance_id, operator):
        if not policy_ids:
            return
        alerts = list(
            MonitorAlert.objects.filter(
                policy_id__in=policy_ids,
                monitor_instance_id=instance_id,
                status="new",
            )
        )
        PolicyService._mark_new_alerts_closed(alerts, operator, "policy_group_member_left")

    @staticmethod
    def has_reported_baseline(policy, instance_id):
        return PolicyInstanceBaseline.objects.filter(policy_id=policy.id, monitor_instance_id=instance_id).exists()
