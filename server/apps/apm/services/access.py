from django.db.models import QuerySet

from apps.core.utils.team_utils import get_current_team
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.virtual_organizations import authorized_virtual_organization_ids

_REQUEST_VISIBLE_ORGANIZATION_IDS = "_apm_visible_organization_ids"


def current_organization_id(request) -> int | None:
    raw_value = get_current_team(request)
    try:
        organization_id = int(raw_value)
    except (TypeError, ValueError):
        return None

    if getattr(request.user, "is_superuser", False):
        return organization_id

    authorized_ids = set(normalize_user_group_ids(getattr(request.user, "group_list", [])))
    return organization_id if organization_id in authorized_ids else None


def visible_organization_ids(request) -> frozenset[int]:
    cached = getattr(request, _REQUEST_VISIBLE_ORGANIZATION_IDS, None)
    if cached is not None:
        return cached

    current_id = current_organization_id(request)
    if current_id is None:
        result = frozenset()
    else:
        result = frozenset({current_id} | authorized_virtual_organization_ids(request.user))
    setattr(request, _REQUEST_VISIBLE_ORGANIZATION_IDS, result)
    return result


def assignable_organization_ids(request) -> set[int]:
    if getattr(request.user, "is_superuser", False):
        return set()
    return set(normalize_user_group_ids(getattr(request.user, "group_list", [])))


def filter_current_organization(queryset: QuerySet, request, relation: str) -> QuerySet:
    organization_ids = visible_organization_ids(request)
    if not organization_ids:
        return queryset.none()
    return queryset.filter(**{f"{relation}__organization__in": organization_ids}).distinct()


def validate_assignable_organizations(request, organization_ids: list[int]) -> None:
    if not organization_ids:
        raise ValueError("至少选择一个组织")
    current_id = current_organization_id(request)
    if current_id is None:
        raise PermissionError("当前组织不在用户授权范围内")
    if getattr(request.user, "is_superuser", False):
        return
    allowed = assignable_organization_ids(request)
    if not set(organization_ids).issubset(allowed):
        raise PermissionError("包含无权分配的组织")
