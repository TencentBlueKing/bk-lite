"""
Compatibility re-export for the enterprise footprint detector.

The actual implementation lives in the side-effect-free module
``apps.core.utils.enterprise_footprint`` so it can be imported without
triggering Django setup or Celery initialisation via this config package.

This wrapper preserves the original public API so that app.py / extra.py
and any other config-package consumers continue to work unchanged.
"""
from apps.core.utils.enterprise_footprint import (  # noqa: F401  re-export
    EnterpriseFootprintError,
    EnterpriseFootprintStatus,
    _is_effective_file,
    detect_enterprise_footprint,
    require_enterprise_license_management,
)
