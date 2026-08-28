"""
Lightweight helper for resolving INSTALL_APPS with enterprise-footprint gating.

No Django models are imported here, making this module importable and testable
without a Django project setup.
"""
import os

from apps.core.utils.enterprise_footprint import EnterpriseFootprintError, detect_enterprise_footprint

# 显式 INSTALL_APPS 裁剪时仍须装入的 always-on 业务 app（与 app.py / extra.py 保持一致）
_ALWAYS_ON_SCAN_APPS = frozenset({"system_mgmt", "console_mgmt"})


def get_install_apps() -> set[str]:
    """Return the set of app names to install, gated on enterprise footprint status."""
    apps = {item.strip() for item in os.getenv("INSTALL_APPS", "").split(",") if item.strip()}
    if apps:
        apps |= _ALWAYS_ON_SCAN_APPS
    status = detect_enterprise_footprint()
    if status.has_enterprise_footprint and not status.license_mgmt_present:
        raise EnterpriseFootprintError(
            f"Detected enterprise footprint in apps: {', '.join(status.enterprise_apps)}, "
            f"but apps/license_mgmt is missing. "
            f"Refuse to start without license management. "
            f"Restore apps/license_mgmt or remove all enterprise content "
            f"to run in community mode."
        )
    if status.should_enable_license_mgmt:
        apps.add("license_mgmt")
    else:
        # Discard any explicit license_mgmt when there is no enterprise footprint,
        # consistent with the gating in app.py (Task 2).
        apps.discard("license_mgmt")
    return apps
