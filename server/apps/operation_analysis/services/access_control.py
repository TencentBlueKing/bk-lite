from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.core.utils.permission_utils import get_permission_rules
from apps.core.utils.user_group import normalize_user_group_ids


def _extract_child_group_ids(group_tree, current_team_id):
    group_ids = []

    def extract_ids(groups, target_id):
        for group in groups:
            if group.get("id") == target_id:
                group_ids.append(target_id)
                if group.get("subGroups"):
                    extract_subgroups(group["subGroups"])
                return True
            if group.get("subGroups") and extract_ids(group["subGroups"], target_id):
                return True
        return False

    def extract_subgroups(subgroups):
        for subgroup in subgroups:
            group_ids.append(subgroup.get("id"))
            if subgroup.get("subGroups"):
                extract_subgroups(subgroup["subGroups"])

    extract_ids(group_tree or [], current_team_id)
    return [group_id for group_id in group_ids if group_id is not None]


def get_scoped_group_ids(user, current_team, include_children=False):
    user_groups = normalize_user_group_ids(getattr(user, "group_list", []))
    if include_children:
        child_groups = _extract_child_group_ids(getattr(user, "group_tree", []), current_team)
        if child_groups:
            user_groups = child_groups
    return user_groups


def build_authorized_queryset(queryset, user, current_team, permission_key, include_children=False, org_field="groups"):
    fields = [field.name for field in queryset.model._meta.fields]
    query = Q()
    scoped_group_ids = get_scoped_group_ids(user, current_team, include_children)

    if "created_by" in fields:
        creator_query = Q(created_by=user.username, domain=user.domain)
        if include_children and scoped_group_ids:
            org_query = Q()
            for group_id in scoped_group_ids:
                org_query |= Q(**{f"{org_field}__contains": int(group_id)})
            query = org_query | creator_query
        else:
            query = Q(**{f"{org_field}__contains": current_team}) | creator_query
    elif org_field in fields:
        query = Q(**{f"{org_field}__contains": current_team})

    permission_data = get_permission_rules(user, current_team, "operation_analysis", permission_key, include_children)
    instance_ids = [item["id"] for item in permission_data.get("instance", [])]
    team_ids = permission_data.get("team", [])

    if not instance_ids and not team_ids:
        return queryset.none()

    if instance_ids:
        query |= Q(id__in=instance_ids)
    for team_id in team_ids:
        query |= Q(**{f"{org_field}__contains": int(team_id)})

    return queryset.filter(query).distinct()


def ensure_instance_view_permission(instance, user, current_team, permission_key, include_children=False, org_field="groups"):
    groups = getattr(instance, org_field, [])
    if not isinstance(groups, list):
        groups = []

    scoped_group_ids = set(get_scoped_group_ids(user, current_team, include_children))
    if groups and not set(groups).intersection(scoped_group_ids):
        raise PermissionDenied("当前用户无权查看该对象")

    permission_data = get_permission_rules(user, current_team, "operation_analysis", permission_key, include_children)
    if int(current_team) in permission_data.get("team", []):
        return

    if include_children:
        allowed_teams = {int(team_id) for team_id in permission_data.get("team", [])}
        allowed_teams.add(int(current_team))
        if scoped_group_ids & allowed_teams:
            return

    instance_ids = {int(item["id"]) for item in permission_data.get("instance", []) if "View" in item.get("permission", [])}
    if instance.id not in instance_ids:
        raise PermissionDenied("当前用户无权查看该对象")
