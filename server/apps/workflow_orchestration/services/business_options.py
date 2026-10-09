from __future__ import annotations

from typing import Any

from apps.core.utils.viewset_utils import build_json_membership_query


def materialize_business_options(catalog: dict[str, dict[str, Any]], team: int) -> None:
    """Add organization-scoped display options without exposing raw resource records."""
    notification = catalog.get("bklite_notification")
    from apps.system_mgmt.models import Channel, User

    if not notification:
        return

    schema = notification.get("input_schema") or {}
    properties = schema.get("properties") or {}
    channel_schema = properties.get("channel_id")
    if isinstance(channel_schema, dict):
        queryset = Channel.objects.all()
        channels = list(
            queryset.filter(build_json_membership_query(queryset, "team", [team])).order_by("name", "id").values("id", "name", "channel_type")[:200]
        )
        if channels:
            channel_schema["enum"] = [item["id"] for item in channels]
            channel_schema["x-enum-labels"] = {str(item["id"]): f"{item['name']} · {item['channel_type']}" for item in channels}

    recipient_schema = properties.get("recipients")
    recipient_items = recipient_schema.get("items") if isinstance(recipient_schema, dict) else None
    if isinstance(recipient_items, dict):
        queryset = User.objects.filter(disabled=False)
        users = list(
            queryset.filter(build_json_membership_query(queryset, "group_list", [team]))
            .only("id", "username", "display_name")
            .order_by("display_name", "username")[:500]
        )
        if users:
            recipient_items["enum"] = [str(item.id) for item in users]
            recipient_items["x-enum-labels"] = {str(item.id): f"{item.display_name or item.username} ({item.username})" for item in users}
            recipient_items["x-enum-usernames"] = {str(item.id): item.username for item in users}
