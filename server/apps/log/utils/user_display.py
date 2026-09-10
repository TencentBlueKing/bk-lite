from apps.system_mgmt.models import User


def _format_user_display(user: dict) -> str:
    username = user.get("username") or str(user.get("id") or "")
    display_name = str(user.get("display_name") or "").strip()
    return f"{display_name}({username})" if display_name else username


def _split_user_identifiers(identifiers):
    ids = []
    usernames = []
    for item in identifiers or []:
        if item is None or item == "":
            continue
        if isinstance(item, bool):
            continue
        if isinstance(item, int) or (isinstance(item, str) and item.isdigit()):
            ids.append(int(item))
        else:
            usernames.append(str(item))
    return ids, usernames


def build_user_display_map(identifiers) -> dict[str, str]:
    ids, usernames = _split_user_identifiers(identifiers)
    if not ids and not usernames:
        return {}

    users = []
    if ids:
        users.extend(User.objects.filter(id__in=ids).values("id", "username", "display_name"))
    if usernames:
        users.extend(User.objects.filter(username__in=usernames).values("id", "username", "display_name"))

    result: dict[str, str] = {}
    for user in users:
        display = _format_user_display(user)
        result[str(user["id"])] = display
        if user.get("username"):
            result[str(user["username"])] = display
    return result


def format_user_identifiers(identifiers, user_map: dict[str, str] | None = None) -> list[str]:
    if not identifiers:
        return []
    resolved_map = user_map if user_map is not None else build_user_display_map(identifiers)
    return [resolved_map.get(str(item), str(item)) for item in identifiers]


def enrich_alerts_handlers_display(alerts: list[dict]) -> None:
    identifiers = []
    for alert in alerts:
        identifiers.extend(alert.get("handlers") or [])
    user_map = build_user_display_map(identifiers)
    for alert in alerts:
        alert["handlers_display"] = format_user_identifiers(alert.get("handlers") or [], user_map)
