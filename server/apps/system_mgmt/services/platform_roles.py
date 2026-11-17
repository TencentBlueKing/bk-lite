from apps.system_mgmt.models import Menu, Role

PLATFORM_ADMIN_ROLE_NAMES = frozenset({"admin", "system-manager--admin"})
PLATFORM_AUDITOR_ROLE_NAMES = frozenset({"auditor", "system-manager--auditor"})


def is_platform_admin(role_names) -> bool:
    return bool(PLATFORM_ADMIN_ROLE_NAMES.intersection(role_names or []))


def is_platform_auditor(role_names) -> bool:
    return bool(PLATFORM_AUDITOR_ROLE_NAMES.intersection(role_names or []))


def ensure_platform_auditor_role() -> Role:
    role, _created = Role.objects.get_or_create(name="auditor", app="", defaults={"menu_list": [], "description": "超级审计员"})
    return role


def is_view_menu(name: str) -> bool:
    return bool(name) and name.rsplit("-", 1)[-1] == "View"


def view_permission_map() -> dict[str, list[str]]:
    perms: dict[str, list[str]] = {}
    for app, name in Menu.objects.values_list("app", "name"):
        if is_view_menu(name):
            perms.setdefault(app, []).append(name)
    return perms
