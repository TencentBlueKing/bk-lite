"""模块内置角色。

角色名是稳定标识。组织是否放开只对当前应用生效，不把用户标成平台超管。
系统管理是平台身份，不放模块角色。
控制台没有菜单，也没有按组织隔离的数据，登录后就能进，不放模块角色。
"""

MODULE_ADMIN_ROLE = "module_admin"
MODULE_AUDITOR_ROLE = "module_auditor"
EXCLUDED_CLIENTS = frozenset({"system-manager", "ops-console"})

_PACKAGE_TO_CLIENT = {
    "system_mgmt": "system-manager",
    "node_mgmt": "node",
    "console_mgmt": "ops-console",
    "operation_analysis": "ops-analysis",
    "job_mgmt": "job",
    "patch_mgmt": "patch",
    "alerts": "alarm",
}


def is_module_builtin_role(name: str) -> bool:
    return name in {MODULE_ADMIN_ROLE, MODULE_AUDITOR_ROLE}


def role_sort_key(name: str):
    if name == MODULE_ADMIN_ROLE:
        return (0, name)
    if name == MODULE_AUDITOR_ROLE:
        return (1, name)
    return (2, name)


def client_id_from_module(module_path: str) -> str:
    parts = (module_path or "").split(".")
    try:
        index = parts.index("apps")
    except ValueError:
        return ""
    if index + 1 >= len(parts):
        return ""
    package = parts[index + 1]
    return _PACKAGE_TO_CLIENT.get(package, package)


def client_id_from_request(request) -> str:
    resolver = getattr(request, "resolver_match", None)
    func = getattr(resolver, "func", None) if resolver else None
    view_cls = getattr(func, "cls", None) or getattr(func, "view_class", None)
    module = getattr(view_cls or func, "__module__", "") if func else ""
    app = client_id_from_module(module)
    if app:
        return app
    from apps.core.backends import AuthBackend

    if not isinstance(getattr(request, "path", None), str):
        return ""
    package = AuthBackend._extract_app_name_from_request(request)
    return _PACKAGE_TO_CLIENT.get(package, package)


def can_assign_module_roles(user) -> bool:
    """只有平台超级管理员可以授予或收回模块管理员 / 模块审计员。"""
    return bool(getattr(user, "is_superuser", False))


class ModuleRoleGrantError(Exception):
    """非平台超管试图更改模块角色。"""


class ModuleRoleIdentityTransitionError(ModuleRoleGrantError):
    """切换平台身份将间接收回已有模块角色。"""


def validate_module_role_change(submitted_ids, existing_ids, module_ids, *, can_assign, identity_transition=False):
    if can_assign:
        return
    submitted_module = set(submitted_ids).intersection(module_ids)
    existing_module = set(existing_ids).intersection(module_ids)
    if submitted_module != existing_module:
        if identity_transition and existing_module - submitted_module:
            raise ModuleRoleIdentityTransitionError()
        raise ModuleRoleGrantError()


def module_builtin_role_ids():
    from apps.system_mgmt.models import Role

    return set(Role.objects.filter(name__in=[MODULE_ADMIN_ROLE, MODULE_AUDITOR_ROLE]).values_list("id", flat=True))


def sanitize_submitted_roles(actor, submitted_ids, existing_ids=None, *, identity_transition=False):
    """非平台超管不能更改模块角色，含通过用户编辑间接收回。"""
    try:
        submitted = [int(role_id) for role_id in (submitted_ids or [])]
        existing = [int(role_id) for role_id in (existing_ids or [])]
    except (TypeError, ValueError) as error:
        raise ModuleRoleGrantError() from error
    if can_assign_module_roles(actor):
        return submitted
    validate_module_role_change(
        submitted,
        existing,
        module_builtin_role_ids(),
        can_assign=False,
        identity_transition=identity_transition,
    )
    return submitted


def module_privilege(role_names, client_id: str, *, platform_auditor=False):
    if not client_id or client_id in EXCLUDED_CLIENTS:
        return None
    names = set(role_names or [])
    if f"{client_id}--{MODULE_ADMIN_ROLE}" in names:
        return "auditor" if platform_auditor else "admin"
    if f"{client_id}--{MODULE_AUDITOR_ROLE}" in names:
        return "auditor"
    return None


def menu_scope_flags(role_names, client_id: str, *, platform_admin: bool, platform_auditor: bool):
    if platform_admin:
        return True, False
    roles = set(role_names or [])
    privilege = module_privilege(roles, client_id)
    if privilege:
        if platform_auditor or privilege == "auditor":
            return False, True
        return True, False
    legacy_admin = f"{client_id}--admin" in roles
    return legacy_admin, platform_auditor and not legacy_admin


def effective_module_privilege(user, client_id: str):
    """平台超级审计员保持只读。模块管理员不能把这个身份抬成可写。"""
    return module_privilege(
        getattr(user, "roles", ()),
        client_id,
        platform_auditor=bool(getattr(user, "is_auditor", False) and not getattr(user, "is_superuser", False)),
    )


def module_apps_from_roles(role_rows):
    admin_apps = set()
    auditor_apps = set()
    for role in role_rows:
        app = getattr(role, "app", "") or ""
        name = getattr(role, "name", "")
        if not app or app in EXCLUDED_CLIENTS:
            continue
        if name == MODULE_ADMIN_ROLE:
            admin_apps.add(app)
        elif name == MODULE_AUDITOR_ROLE:
            auditor_apps.add(app)
    return admin_apps, auditor_apps - admin_apps


def overlay_module_permissions(permission, admin_apps, auditor_apps) -> dict:
    """管理员补齐该应用全部菜单。审计员只保留该应用的查看菜单。"""
    if not admin_apps and not auditor_apps:
        return {app: list(names) for app, names in (permission or {}).items()}

    from apps.system_mgmt.models import Menu
    from apps.system_mgmt.services.platform_roles import is_view_menu

    normalized = {app: set(names or []) for app, names in (permission or {}).items()}
    if admin_apps:
        for app, name in Menu.objects.filter(app__in=list(admin_apps)).values_list("app", "name"):
            normalized.setdefault(app, set()).add(name)
    for app in auditor_apps:
        view_names = {name for name in Menu.objects.filter(app=app).values_list("name", flat=True) if is_view_menu(name)}
        normalized[app] = view_names
    return {app: sorted(names) for app, names in normalized.items()}
