"""补丁自定义 action 对批量对象 ID 的框架权限校验。"""

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.utils import viewset_utils
from apps.core.utils.team_utils import get_current_team
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.patch_mgmt.utils.i18n import patch_message


def require_authorized_ids(
    view, request, queryset, ids, permission_key, operation="Operate"
):
    """确认所有请求 ID 均具备指定的实例数据权限。"""
    try:
        requested = {int(value) for value in ids if value is not None}
    except (TypeError, ValueError) as exc:
        raise ValidationError(patch_message(request, "error.data_id_integer", "Data ID must be an integer")) from exc

    scoped_queryset = view.get_queryset_by_permission(
        request,
        queryset.filter(pk__in=requested),
        permission_key=permission_key,
    )
    if getattr(request.user, "is_superuser", False) or operation == "View":
        authorized_queryset = scoped_queryset
    else:
        current_team = get_current_team(request, "0")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        rules = viewset_utils.get_permission_rules(
            request.user,
            current_team,
            view._get_app_name(),
            permission_key,
            include_children,
        )
        instance_ids = [
            item.get("id")
            for item in rules.get("instance", [])
            if operation in (item.get("permission") or [])
        ]
        team_query = build_json_membership_query(
            queryset, view.ORGANIZATION_FIELD, rules.get("team", [])
        )
        authorized_queryset = scoped_queryset.filter(
            team_query | Q(pk__in=instance_ids)
        )

    authorized = set(authorized_queryset.values_list("pk", flat=True))
    denied = sorted(requested - authorized)
    if denied:
        raise PermissionDenied(patch_message(request, "error.data_access_denied", "You do not have access to the selected data: {ids}", ids=denied))
    return requested
