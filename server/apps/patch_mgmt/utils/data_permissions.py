"""补丁自定义 action 对批量对象 ID 的框架权限校验。"""

from rest_framework.exceptions import PermissionDenied, ValidationError


def require_authorized_ids(view, request, queryset, ids, permission_key):
    """确认所有请求 ID 都在公共 ``AuthViewSet`` 授权查询集中。"""
    try:
        requested = {int(value) for value in ids if value is not None}
    except (TypeError, ValueError) as exc:
        raise ValidationError("数据 ID 必须为整数") from exc

    authorized = set(
        view.get_queryset_by_permission(
            request,
            queryset.filter(pk__in=requested),
            permission_key=permission_key,
        ).values_list("pk", flat=True)
    )
    denied = sorted(requested - authorized)
    if denied:
        raise PermissionDenied(f"无权访问所选数据: {denied}")
    return requested
