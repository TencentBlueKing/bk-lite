from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response


def _validate_groups_payload(data):
    groups = data.get("groups")
    if not isinstance(groups, list) or any(type(group_id) is not int or group_id <= 0 for group_id in groups):
        raise ValidationError({"groups": ["必须是正整数 ID 数组"]})
    return {"groups": groups}


def partial_update_groups_with_auth(viewset, request, instance):
    """锁内校验并更新内置对象的组织可见性；内置对象不维护实例权限规则。"""
    groups_data = _validate_groups_payload(request.data)
    with transaction.atomic():
        locked_instance = viewset.get_queryset().select_for_update().get(pk=instance.pk)
        if not getattr(request.user, "is_superuser", False):
            access_error = viewset._validate_update_access(request, locked_instance, groups_data)
            if access_error is not None:
                return access_error

        serializer = viewset.get_serializer(locked_instance, data=groups_data, partial=True)
        serializer.is_valid(raise_exception=True)
        viewset.perform_update(serializer)

    if getattr(locked_instance, "_prefetched_objects_cache", None):
        locked_instance._prefetched_objects_cache = {}
    return Response(serializer.data)
