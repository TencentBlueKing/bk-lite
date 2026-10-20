from django.apps import apps
from django.conf import settings

from apps.core.logger import module_link_logger as logger
from apps.core.utils.web_utils import WebUtils
from apps.module_link.license_policy import (
    LICENSE_DENIED_TEMPLATE,
    PARENT_LICENSE_APPS,
    apply_module_link_license_exempt,
    is_module_link_api,
    missing_parent_licenses,
)

_LOOKUP_FAILED = "event=module_link_license_inherit_lookup_failed error_type=%s"
_DENIED = "event=module_link_license_inherit_denied missing=%s"


def _license_guard_active() -> bool:
    if not getattr(settings, "LICENSE_MGMT_ENABLED", True):
        return False
    return apps.is_installed("apps.license_mgmt")


def _licensed_names():
    from apps.license_mgmt.middleware.license_guard import get_licensed_names

    return get_licensed_names() or ()


def _deny(app_name: str):
    return WebUtils.response_403(LICENSE_DENIED_TEMPLATE % app_name)


class ModuleLinkLicenseInheritMiddleware:
    """Glue APIs inherit cmdb+monitor licenses instead of being a sellable SKU."""

    def __init__(self, get_response):
        self.get_response = get_response
        apply_module_link_license_exempt()

    def __call__(self, request):
        path = getattr(request, "path_info", None) or getattr(request, "path", "") or ""
        if not is_module_link_api(path):
            return self.get_response(request)
        if not _license_guard_active():
            return self.get_response(request)
        try:
            names = _licensed_names()
        except Exception as exc:
            logger.debug(_LOOKUP_FAILED, type(exc).__name__)
            return _deny(PARENT_LICENSE_APPS[0])
        missing = missing_parent_licenses(names)
        if missing:
            logger.debug(_DENIED, ",".join(missing))
            return _deny(missing[0])
        return self.get_response(request)
