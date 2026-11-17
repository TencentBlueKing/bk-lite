"""工作台流程输入的回复语言。页面和 API 入口不经过这里。"""

from apps.system_mgmt.models import User

WORKBENCH_DEFAULT_LOCALE = "zh-Hans"


def _stored_locale(user) -> str:
    return str(getattr(user, "locale", "") or "").strip()


def locale_for_user_ids(user_ids) -> str:
    """按原顺序用数字主键查用户。空语言跳过，都没有则用简体中文。"""
    ordered_ids: list[int] = []
    seen: set[int] = set()
    for user_id in user_ids or []:
        if user_id is None:
            continue
        raw = str(user_id).strip()
        if not raw.isdigit():
            continue
        pk = int(raw)
        if pk in seen:
            continue
        seen.add(pk)
        ordered_ids.append(pk)
    if not ordered_ids:
        return WORKBENCH_DEFAULT_LOCALE

    rows = User.objects.filter(id__in=ordered_ids).only("id", "locale")
    by_id = {row.id: row for row in rows}
    for pk in ordered_ids:
        user = by_id.get(pk)
        if user is None:
            continue
        locale = _stored_locale(user)
        if locale:
            return locale
    return WORKBENCH_DEFAULT_LOCALE


def locale_for_creator(username: str | None, domain: str | None) -> str:
    """按用户名和域查机器人创建者。查不到或语言为空时用简体中文。"""
    name = str(username or "").strip()
    if not name:
        return WORKBENCH_DEFAULT_LOCALE
    user = User.objects.filter(username=name, domain=domain or "").only("locale").first()
    if user is None:
        return WORKBENCH_DEFAULT_LOCALE
    return _stored_locale(user) or WORKBENCH_DEFAULT_LOCALE
