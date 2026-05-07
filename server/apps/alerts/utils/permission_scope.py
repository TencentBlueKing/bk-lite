from django.db.models import Q

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
    result = get_authorized_groups_scoped(_get_actor_context(request), include_children=include_children)
    if not result.get("result"):
        return []

    group_ids = []
    for group_id in result.get("data", []):
        try:
            group_ids.append(int(group_id))
        except (TypeError, ValueError):
            continue
    return group_ids


def filter_alert_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset

    username = getattr(user, "username", "")
    query = Q()
    if username:
        query |= Q(operator__contains=username)

    for group_id in get_authorized_group_ids(request):
        query |= Q(team__contains=group_id)

    if not query.children:
        return queryset.none()
    return queryset.filter(query).distinct()


def filter_incident_queryset_for_request(queryset, request):
    user = getattr(request, "user", None)
    if not user:
        return queryset.none()
    if getattr(user, "is_superuser", False):
        return queryset.distinct()

    username = getattr(user, "username", "")
    query = Q()
    if username:
        query |= Q(operator__contains=username) | Q(alert__operator__contains=username)

    for group_id in get_authorized_group_ids(request):
        query |= Q(alert__team__contains=group_id)

    if not query.children:
        return queryset.none()
    return queryset.filter(query).distinct()
