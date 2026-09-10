"""告警可见性：组织在生成时快照，与策略当前组织权限解耦。"""

from django.db.models import Q

from apps.core.constants import DEFAULT_PERMISSION
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.monitor.models.monitor_policy import MonitorPolicy


def snapshot_policy_organization_ids(policy) -> list[int]:
    related = getattr(policy, "policyorganization_set", None)
    ids = []
    if related is not None:
        ids = [int(value) for value in related.values_list("organization", flat=True)]
    if ids:
        return sorted(set(ids))
    extra = getattr(policy, "organizations", None) or []
    return sorted({int(value) for value in extra if value not in (None, "")})


def filter_alerts_by_organizations(queryset, organization_ids, *, field_name="organizations"):
    return queryset.filter(build_json_membership_query(queryset, field_name, organization_ids))


def orphaned_monitor_policy_q():
    return ~Q(policy_id__in=MonitorPolicy.objects.values("id"))


def instance_permission_alert_q(permissions_data, organization_ids, *, require_operate=False):
    """在组织快照已过滤的前提下，叠加对象级策略权限；策略已删除的告警仍可见。"""
    if not isinstance(permissions_data, dict) or not permissions_data:
        return Q(pk__in=[])

    scope_ids = {int(value) for value in organization_ids or [] if value not in (None, "")}
    admin_teams = {int(value) for value in (permissions_data.get("all") or {}).get("team", []) or [] if value not in (None, "")}
    if admin_teams & scope_ids:
        return Q()

    granted_policy_ids = []
    team_level_object_ids = []
    for object_type_id, permission in permissions_data.items():
        if object_type_id == "all" or not isinstance(permission, dict):
            continue
        team_perm = {int(value) for value in (permission.get("team") or []) if value not in (None, "")}
        if team_perm & scope_ids:
            try:
                team_level_object_ids.append(int(object_type_id))
            except (TypeError, ValueError):
                pass
        for instance in permission.get("instance") or []:
            if not isinstance(instance, dict):
                continue
            perms = instance.get("permission") or DEFAULT_PERMISSION
            if require_operate and "Operate" not in perms:
                continue
            if not perms:
                continue
            instance_id = instance.get("id")
            if instance_id in (None, ""):
                continue
            granted_policy_ids.append(instance_id)

    query = Q(policy_id__in=granted_policy_ids)
    if team_level_object_ids:
        query |= Q(policy_id__in=MonitorPolicy.objects.filter(monitor_object_id__in=team_level_object_ids).values("id"))
    return query | orphaned_monitor_policy_q()


def visible_monitor_alerts(queryset, *, organization_ids, is_superuser, permissions_data=None, require_operate=False):
    queryset = filter_alerts_by_organizations(queryset, organization_ids)
    if is_superuser:
        return queryset
    return queryset.filter(
        instance_permission_alert_q(
            permissions_data,
            organization_ids,
            require_operate=require_operate,
        )
    ).distinct()
