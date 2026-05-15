from apps.system_mgmt.models.user import User


def normalize_usernames(usernames):
    if usernames in (None, ""):
        return []
    if isinstance(usernames, str):
        usernames = [usernames]
    if not isinstance(usernames, list):
        return []

    normalized = []
    seen = set()
    for username in usernames:
        if not isinstance(username, str):
            continue
        username = username.strip()
        if not username or username in seen:
            continue
        seen.add(username)
        normalized.append(username)
    return normalized


def normalize_group_ids(group_values):
    normalized = set()
    for group in group_values or []:
        group_id = group.get("id") if isinstance(group, dict) else group
        try:
            normalized.add(int(group_id))
        except (TypeError, ValueError):
            continue
    return normalized


def _build_missing_users_message(usernames):
    return f"以下处理人不存在: {', '.join(usernames)}"


def _build_out_of_scope_message(usernames, scope_name):
    return f"以下处理人不在{scope_name}组织范围内: {', '.join(usernames)}"


def validate_usernames_in_groups(usernames, allowed_group_ids, scope_name):
    normalized_usernames = normalize_usernames(usernames)
    if not normalized_usernames:
        return normalized_usernames, None

    user_map = {
        item["username"]: normalize_group_ids(item["group_list"])
        for item in User.objects.filter(username__in=normalized_usernames).values("username", "group_list")
    }

    missing_users = [username for username in normalized_usernames if username not in user_map]
    if missing_users:
        return normalized_usernames, _build_missing_users_message(missing_users)

    invalid_users = [username for username in normalized_usernames if not user_map[username].intersection(allowed_group_ids)]
    if invalid_users:
        return normalized_usernames, _build_out_of_scope_message(invalid_users, scope_name)

    return normalized_usernames, None


def validate_alert_assignees(alert, usernames):
    allowed_group_ids = normalize_group_ids(getattr(alert, "team", []))
    return validate_usernames_in_groups(usernames, allowed_group_ids, "告警所属")


def validate_incident_operators(alerts, usernames):
    allowed_group_ids = set()
    for alert in alerts:
        allowed_group_ids.update(normalize_group_ids(getattr(alert, "team", [])))
    return validate_usernames_in_groups(usernames, allowed_group_ids, "事故关联告警")
