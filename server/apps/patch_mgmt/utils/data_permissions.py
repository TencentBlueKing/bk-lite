"""补丁自定义 action 对批量对象 ID 的框架权限校验。"""

from rest_framework.exceptions import PermissionDenied, ValidationError
from apps.patch_mgmt.utils.i18n import patch_message


def require_authorized_ids(view, request, queryset, ids, permission_key):
    """确认所有请求 ID 都在公共 ``AuthViewSet`` 授权查询集中。"""
    try:
        requested = {int(value) for value in ids if value is not None}
    except (TypeError, ValueError) as exc:
        raise ValidationError(patch_message(request, "error.data_id_integer", "Data ID must be an integer")) from exc

    authorized = set(
        view.get_queryset_by_permission(
            request,
            queryset.filter(pk__in=requested),
            permission_key=permission_key,
        ).values_list("pk", flat=True)
    )
    denied = sorted(requested - authorized)
    if denied:
        raise PermissionDenied(patch_message(request, "error.data_access_denied", "You do not have access to the selected data: {ids}", ids=denied))
    return requested
