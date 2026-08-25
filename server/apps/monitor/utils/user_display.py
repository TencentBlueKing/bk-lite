from apps.system_mgmt.models import User


def _format_user_display(user: dict) -> str:
    username = user.get("username") or str(user.get("id") or "")
    display_name = str(user.get("display_name") or "").strip()
    return f"{display_name}({username})" if display_name else username


def _split_notice_user_identifiers(identifiers):
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
    """将 notice_users 中的用户 ID / 用户名解析为展示名。"""
    ids, usernames = _split_notice_user_identifiers(identifiers)
    if not ids and not usernames:
        return {}

    users = []
    if ids:
        users.extend(
            User.objects.filter(id__in=ids).values("id", "username", "display_name")
        )
    if usernames:
        users.extend(
            User.objects.filter(username__in=usernames).values(
                "id", "username", "display_name"
            )
        )

    result: dict[str, str] = {}
    for user in users:
        display = _format_user_display(user)
        result[str(user["id"])] = display
        if user.get("username"):
            result[str(user["username"])] = display
    return result


def format_notice_users(notice_users, user_map: dict[str, str] | None = None) -> list[str]:
    """按存储顺序输出通知人展示名；无法解析时回退为原始标识。"""
    if not notice_users:
        return []
    resolved_map = user_map if user_map is not None else build_user_display_map(notice_users)
    return [resolved_map.get(str(item), str(item)) for item in notice_users]


def resolve_alert_notice_users(alert: dict) -> list:
    """告警自身 notice_users 优先，否则回退策略配置。"""
    alert_users = alert.get("notice_users") or []
    if alert_users:
        return alert_users
    policy = alert.get("policy") or {}
    return policy.get("notice_users") or []


def enrich_alerts_notice_users_display(alerts: list[dict]) -> None:
    """就地为告警列表补充 notice_users_display，供前端直接展示。"""
    identifiers = []
    for alert in alerts:
        identifiers.extend(resolve_alert_notice_users(alert))
    user_map = build_user_display_map(identifiers)
    for alert in alerts:
        alert["notice_users_display"] = format_notice_users(
            resolve_alert_notice_users(alert),
            user_map,
        )
