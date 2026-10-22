MODULE_LINK_API_PREFIX = "/api/v1/module_link/"
PARENT_LICENSE_APPS = ("cmdb", "monitor")
LICENSE_DENIED_TEMPLATE = "Module '%s' requires a valid license"
INHERIT_MIDDLEWARE = "apps.module_link.middleware.ModuleLinkLicenseInheritMiddleware"
APP_GUARD_MIDDLEWARE = "apps.license_mgmt.middleware.license_guard.LicenseAppGuardMiddleware"


def is_module_link_api(path: str) -> bool:
    return (path or "").startswith(MODULE_LINK_API_PREFIX)


def missing_parent_licenses(licensed_names) -> tuple[str, ...]:
    names = {str(item) for item in (licensed_names or ())}
    return tuple(app for app in PARENT_LICENSE_APPS if app not in names)


def _load_license_guard():
    from apps.license_mgmt.middleware import license_guard

    return license_guard


def apply_module_link_license_exempt(guard_module=None) -> bool:
    """Let EE LicenseAppGuard skip glue URLs so they are not treated as a sellable SKU."""
    if guard_module is None:
        from django.apps import apps

        # 社区版目录还在，但没有装入这个 app。直接导入会在模型声明时抛 RuntimeError。
        if not apps.is_installed("apps.license_mgmt"):
            return False
    try:
        module = _load_license_guard() if guard_module is None else guard_module
    except ImportError:
        return False
    prefixes = getattr(module, "LICENSE_EXEMPT_PREFIXES", None)
    if not isinstance(prefixes, (tuple, list)):
        return False
    if MODULE_LINK_API_PREFIX in prefixes:
        return True
    module.LICENSE_EXEMPT_PREFIXES = tuple(prefixes) + (MODULE_LINK_API_PREFIX,)
    return True


def inject_inherit_middleware(django_settings) -> bool:
    """Insert inherit middleware before EE app guard even when app.py is encrypted."""
    current = list(getattr(django_settings, "MIDDLEWARE", ()) or ())
    if INHERIT_MIDDLEWARE in current:
        return True
    if APP_GUARD_MIDDLEWARE not in current:
        return False
    current.insert(current.index(APP_GUARD_MIDDLEWARE), INHERIT_MIDDLEWARE)
    django_settings.MIDDLEWARE = tuple(current)
    return True
