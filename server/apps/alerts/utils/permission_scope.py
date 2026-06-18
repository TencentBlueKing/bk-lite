from django.db import connection
from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.alerts.constants.constants import LogTargetType
from apps.alerts.models.models import Alert, Incident
from apps.system_mgmt.utils.group_utils import GroupUtils
from apps.core.utils.team_utils import get_current_team


def get_current_team_from_request(request, required=False):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        return None if not required else 0
    try:
        return int(current_team)
    except (TypeError, ValueError):
        return None if not required else 0


def get_query_group_ids(request):
    current_team = get_current_team_from_request(request, required=False)
    if not current_team:
        return []

    user = getattr(request, "user", None)
    if user is None:
        return []

    if not getattr(user, "is_superuser", False):
        user_group_ids = {group["id"] for group in getattr(user, "group_list", [])}
        if current_team not in user_group_ids:
            raise PermissionDenied("无权访问该团队数据")

    include_children = request.COOKIES.get("include_children", "0") == "1"
    if include_children:
        group_tree = getattr(user, "group_tree", [])
        if group_tree:
            return extract_child_group_ids(group_tree, current_team) or [current_team]
        return GroupUtils.get_group_with_descendants(current_team)
    return [current_team]


def get_authorized_group_ids(request):
    return get_query_group_ids(request)


def normalize_team_ids(team_ids):
    if team_ids in (None, ""):
        return []
    if not isinstance(team_ids, list):
        raise ValueError("team must be a list of ids.")

    normalized = []
    for team_id in team_ids:
        try:
            normalized.append(int(team_id))
        except (TypeError, ValueError):
            raise ValueError("team must be a list of ids.")
    return normalized


def extract_child_group_ids(group_tree, current_team_id):
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

    extract_ids(group_tree, current_team_id)
    return group_ids


def apply_team_scope_with_group_ids(queryset, group_ids, field_name="team"):
    if not group_ids:
        return queryset.none()
    if connection.features.supports_json_field_contains:
        team_query = _build_team_query(field_name, group_ids)
        if not team_query.children:
            return queryset.none()
        return queryset.filter(team_query).distinct()
    return _filter_json_membership_fallback(queryset, field_name, group_ids).distinct()


def apply_team_scope_for_request(queryset, request, field_name="team"):
    return apply_team_scope_with_group_ids(queryset, get_query_group_ids(request), field_name=field_name)


def _build_team_query(field_name, group_ids):
    if not group_ids:
        return Q()

    team_query = Q()
    for team_id in group_ids:
        team_query |= Q(**{f"{field_name}__contains": [team_id]}) | Q(**{f"{field_name}__contains": [str(team_id)]})
    return team_query


def _filter_json_membership_fallback(queryset, field_name, expected_values):
    expected_set = {value for value in expected_values if value not in (None, "")}
    if not expected_set:
        return queryset.none()

    matched_ids = []
    for item in queryset.only("id", field_name):
        current_values = getattr(item, field_name, []) or []
        if isinstance(current_values, str):
            current_values = [current_values]
        current_values_normalized = set()
        for v in current_values:
            current_values_normalized.add(v)
            try:
                current_values_normalized.add(int(v))
            except (TypeError, ValueError):
                pass
            current_values_normalized.add(str(v))

        if expected_set.intersection(current_values_normalized):
            matched_ids.append(item.pk)
    return queryset.filter(pk__in=matched_ids)


def filter_alert_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    return apply_team_scope_for_request(queryset, request)


def filter_incident_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    return apply_team_scope_for_request(queryset, request)


def filter_event_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    return apply_team_scope_for_request(queryset, request)


def filter_operator_log_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()

    current_team = get_current_team_from_request(request, required=False)
    if not current_team:
        return queryset.none()

    scoped_alert_ids = list(filter_alert_queryset_for_request(Alert.objects.all(), request).values_list("alert_id", flat=True))
    scoped_incident_ids = list(filter_incident_queryset_for_request(Incident.objects.all(), request).values_list("incident_id", flat=True))
    if not scoped_alert_ids and not scoped_incident_ids:
        return queryset.none()

    query = Q()
    if scoped_alert_ids:
        query |= Q(target_type=LogTargetType.ALERT, target_id__in=scoped_alert_ids)
    if scoped_incident_ids:
        query |= Q(target_type=LogTargetType.INCIDENT, target_id__in=scoped_incident_ids)
    return queryset.filter(query).distinct()
