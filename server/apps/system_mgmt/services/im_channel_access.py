from django.db import connection
from django.db.models import Q


def get_user_group_ids(user) -> set[int] | None:
    if getattr(user, "is_superuser", False):
        return None
    return {int(item["id"]) for item in getattr(user, "group_list", []) if str(item.get("id", "")).isdigit()}


def can_access_im_channel(user, channel) -> bool:
    group_ids = get_user_group_ids(user)
    return group_ids is None or bool(group_ids.intersection({int(item) for item in channel.team or []}))


def filter_accessible_im_channels(queryset, user):
    group_ids = get_user_group_ids(user)
    if group_ids is None:
        return queryset
    if not group_ids:
        return queryset.none()

    if not connection.features.supports_json_field_contains:
        channel_ids = [
            channel_id
            for channel_id, team in queryset.values_list("id", "team")
            if group_ids.intersection({int(item) for item in team or []})
        ]
        return queryset.filter(id__in=channel_ids)

    query = Q()
    for group_id in group_ids:
        query |= Q(team__contains=group_id)
    return queryset.filter(query)
