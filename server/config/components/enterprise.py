"""
Centralized enterprise footprint detector.

Scans server/apps/*/enterprise directories for effective enterprise content.
Any file other than __init__.py (and ignoring hidden paths and __pycache__)
counts as enterprise content.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class EnterpriseFootprintError(RuntimeError):
    """Raised when enterprise content is detected but apps/license_mgmt is missing."""


@dataclass
class EnterpriseFootprintStatus:
    enterprise_apps: list[str] = field(default_factory=list)
    license_mgmt_present: bool = False

    @property
    def has_enterprise_footprint(self) -> bool:
        return bool(self.enterprise_apps)

    @property
    def should_enable_license_mgmt(self) -> bool:
        return self.has_enterprise_footprint and self.license_mgmt_present


def _is_effective_file(path: Path) -> bool:
    """Return True if path counts as effective enterprise content."""
    # Ignore hidden files/dirs anywhere in the path
    for part in path.parts:
        if part.startswith("."):
            return False
    # Ignore __pycache__ anywhere in the path
    if "__pycache__" in path.parts:
        return False
    # Ignore __init__.py
    if path.name == "__init__.py":
        return False
    return True


def detect_enterprise_footprint(base_dir=None) -> EnterpriseFootprintStatus:
    """
    Scan <base_dir>/apps/*/enterprise for effective enterprise content.

    base_dir defaults to the parent of this file's config/ package,
    i.e. the server/ directory.
    """
    if base_dir is None:
        # server/config/components/enterprise.py -> server/
        base_dir = Path(__file__).resolve().parent.parent.parent
    else:
        base_dir = Path(base_dir)

    apps_dir = base_dir / "apps"
    enterprise_apps: list[str] = []

    if apps_dir.is_dir():
        for app_dir in sorted(apps_dir.iterdir()):
            if not app_dir.is_dir():
                continue
            enterprise_dir = app_dir / "enterprise"
            if not enterprise_dir.is_dir():
                continue
            # Walk recursively and look for effective files
            for root, dirs, files in os.walk(enterprise_dir):
                root_path = Path(root)
                # Prune hidden dirs and __pycache__ in-place
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
                for fname in files:
                    candidate = root_path / fname
                    # Build relative path from enterprise_dir for clean checks
                    rel = candidate.relative_to(enterprise_dir)
                    if _is_effective_file(rel):
                        enterprise_apps.append(app_dir.name)
                        break  # one effective file is enough for this app
                else:
                    continue
                break  # already found for this app

    license_mgmt_present = (apps_dir / "license_mgmt").is_dir()

    return EnterpriseFootprintStatus(
        enterprise_apps=enterprise_apps,
        license_mgmt_present=license_mgmt_present,
    )


def require_enterprise_license_management(base_dir=None) -> None:
    """
    Raise EnterpriseFootprintError if enterprise content is detected
    but apps/license_mgmt is absent.
    """
    status = detect_enterprise_footprint(base_dir=base_dir)
    if status.has_enterprise_footprint and not status.license_mgmt_present:
        apps_list = ", ".join(status.enterprise_apps)
        raise EnterpriseFootprintError(
            f"Detected enterprise footprint in apps: {apps_list}, "
            f"but apps/license_mgmt is missing. "
            f"Refuse to start without license management. "
            f"Restore apps/license_mgmt or remove all enterprise content "
            f"to run in community mode."
        )
