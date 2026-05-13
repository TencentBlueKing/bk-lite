from django.db import connection
from django.db.models import Q

from apps.alerts.constants.constants import LogTargetType
from apps.alerts.models.models import Alert, Incident
from apps.system_mgmt.nats_api import get_authorized_groups_scoped


def _get_actor_context(request):
    user = getattr(request, "user", None)
    return {
        "username": getattr(user, "username", ""),
        "domain": getattr(user, "domain", "domain.com"),
        "current_team": request.COOKIES.get("current_team"),
        "is_superuser": getattr(user, "is_superuser", False),
    }


def get_authorized_group_ids(request):
    user = getattr(request, "user", None)
    if not user:
        return []
    if getattr(user, "is_superuser", False):
        current_team = request.COOKIES.get("current_team")
        try:
            return [int(current_team)] if current_team not in (None, "") else []
        except (TypeError, ValueError):
            return []

    include_children = request.COOKIES.get("include_children", "0") == "1"
    result = get_authorized_groups_scoped(
        _get_actor_context(request),
        include_children=include_children,
    )
    if not result.get("result"):
        return []

    group_ids = []
    for group_id in result.get("data", []):
        try:
            group_ids.append(int(group_id))
        except (TypeError, ValueError):
            continue
    return group_ids


def _filter_json_membership_fallback(queryset, field_name, expected_values):
    expected_set = {value for value in expected_values if value not in (None, "")}
    if not expected_set:
        return queryset.none()

    matched_ids = []
    for item in queryset.only("id", field_name):
        current_values = getattr(item, field_name, []) or []
        if isinstance(current_values, str):
            current_values = [current_values]
        if expected_set.intersection(set(current_values)):
            matched_ids.append(item.pk)
    return queryset.filter(pk__in=matched_ids)


def filter_alert_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset

    username = getattr(user, "username", "")
    group_ids = get_authorized_group_ids(request)
    if connection.features.supports_json_field_contains:
        query = Q()
        if username:
            query |= Q(operator__contains=username)

        for group_id in group_ids:
            query |= Q(team__contains=group_id)

        if not query.children:
            return queryset.none()
        return queryset.filter(query).distinct()

    scoped_by_operator = _filter_json_membership_fallback(queryset, "operator", [username]) if username else queryset.none()
    scoped_by_team = _filter_json_membership_fallback(queryset, "team", group_ids) if group_ids else queryset.none()
    allowed_ids = set(scoped_by_operator.values_list("pk", flat=True)) | set(scoped_by_team.values_list("pk", flat=True))
    if not allowed_ids:
        return queryset.none()
    return queryset.filter(pk__in=allowed_ids).distinct()


def filter_incident_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset.distinct()

    username = getattr(user, "username", "")
    scoped_alerts = filter_alert_queryset_for_request(Alert.objects.all(), request)
    scoped_alert_ids = list(scoped_alerts.values_list("id", flat=True))
    if connection.features.supports_json_field_contains:
        query = Q()
        if username:
            query |= Q(operator__contains=username)

        if scoped_alert_ids:
            query |= Q(alert__in=scoped_alert_ids)

        if not query.children:
            return queryset.none()
        return queryset.filter(query).distinct()

    scoped_queryset = queryset.filter(alert__in=scoped_alert_ids).distinct() if scoped_alert_ids else queryset.none()
    scoped_ids = set(scoped_queryset.values_list("pk", flat=True))
    operator_ids = set()
    if username:
        operator_ids = set(_filter_json_membership_fallback(queryset, "operator", [username]).values_list("pk", flat=True))

    matched_ids = scoped_ids | operator_ids
    if not matched_ids:
        return queryset.none()
    return queryset.filter(pk__in=matched_ids).distinct()


def filter_event_queryset_for_request(queryset, request):
    scoped_alerts = filter_alert_queryset_for_request(Alert.objects.all(), request)
    return queryset.filter(alert__in=scoped_alerts).distinct()


def filter_operator_log_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset

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
