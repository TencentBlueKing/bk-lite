def has_unrestricted_org_scope(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_auditor", False))


def bypasses_write_guard(user) -> bool:
    return bool(getattr(user, "is_superuser", False))
