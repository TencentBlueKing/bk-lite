"""
MLOps group-scope helpers.

Reusable utilities for team-based ownership filtering in the mlops app.
Mirrors the cookie-parsing behaviour of
``apps.core.utils.viewset_utils.GenericViewSetFun._parse_current_team_cookie``
so that mlops-specific code does not depend on the core ViewSet class hierarchy.
"""

import logging

from rest_framework import serializers

logger = logging.getLogger(__name__)


def get_current_team(request, default=0):
    """Parse ``current_team`` from *request.COOKIES* and return an ``int``.

    Args:
        request: Django/DRF request object.
        default: Value returned when the cookie is missing or non-numeric.

    Returns:
        int – the parsed team id, or *default*.
    """
    raw = request.COOKIES.get("current_team", "")
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def get_allowed_team_ids(request):
    """Return the team ids a user is allowed to assign to root resources."""
    user = getattr(request, "user", None)
    if not user:
        return set()
    if getattr(user, "is_superuser", False):
        return None

    group_list = getattr(user, "group_list", None) or []
    allowed_ids = set()
    for item in group_list:
        if isinstance(item, dict):
            group_id = item.get("id")
        else:
            group_id = item
        if group_id is None:
            continue
        try:
            allowed_ids.add(int(group_id))
        except (TypeError, ValueError):
            continue
    return allowed_ids


def validate_requested_teams(request, team_ids, field_name="team"):
    """Validate an explicit list of teams submitted for a root-owned resource."""
    if not isinstance(team_ids, list) or not team_ids:
        raise serializers.ValidationError({field_name: "必须选择至少一个组织"})

    normalized = []
    for team_id in team_ids:
        try:
            normalized.append(int(team_id))
        except (TypeError, ValueError):
            raise serializers.ValidationError({field_name: "组织ID必须为整数"})

    return normalized


def filter_queryset_by_parent_team(queryset, request, parent_team_lookup):
    """Filter a queryset so that only rows whose parent's ``team`` field
    contains the current team are returned.

    This is the reusable building-block for *inherited* ownership: child
    resources (TrainData, DatasetRelease) that do not carry their own
    ``team`` column can be scoped by looking up the parent's team through
    a Django ORM lookup path.

    Args:
        queryset: A Django ``QuerySet``.
        request: Django/DRF request (used to read the ``current_team`` cookie).
        parent_team_lookup: Dot-free Django ORM lookup prefix pointing at
            the parent's ``team`` JSON field, e.g. ``"dataset__team"`` or
            plain ``"team"`` for root-owned models.

    Returns:
        A filtered ``QuerySet``.
    """
    user = getattr(request, "user", None)
    if getattr(user, "is_superuser", False):
        return queryset

    current_team = get_current_team(request)
    return queryset.filter(**{f"{parent_team_lookup}__contains": current_team})


def assert_team_ownership(team_owned_obj, current_team, field_name, request=None):
    """Raise ``ValidationError`` when ``team_owned_obj`` is not visible to the current team."""
    user = getattr(request, "user", None) if request is not None else None
    if getattr(user, "is_superuser", False):
        return

    owned_teams = getattr(team_owned_obj, "team", None) or []
    if current_team not in owned_teams:
        raise serializers.ValidationError({field_name: "所选资源不属于当前组"})


def assert_parent_team_matches(team_owned_obj, parent_obj, field_name):
    """Raise ``ValidationError`` when a root-owned object does not match its parent's team."""
    owner_team = getattr(team_owned_obj, "team", None) or []
    parent_team = getattr(parent_obj, "team", None) or []
    if owner_team != parent_team:
        raise serializers.ValidationError({field_name: "关联资源与当前对象的组归属不一致"})
