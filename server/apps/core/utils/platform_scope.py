def has_unrestricted_org_scope(user, app=None) -> bool:
    if getattr(user, "is_superuser", False) or getattr(user, "is_auditor", False):
        return True
    if not app:
        return False
    from apps.core.utils.module_scope import module_privilege

    return module_privilege(getattr(user, "roles", ()), app) in {"admin", "auditor"}


def bypasses_write_guard(user, app=None) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    if not app:
        return False
    from apps.core.utils.module_scope import effective_module_privilege

    return effective_module_privilege(user, app) == "admin"


def is_readonly_scope(user, app=None) -> bool:
    if bypasses_write_guard(user, app):
        return False
    if getattr(user, "is_auditor", False):
        return True
    if not app:
        return False
    from apps.core.utils.module_scope import effective_module_privilege

    return effective_module_privilege(user, app) == "auditor"
