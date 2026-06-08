import os
from pathlib import Path

from config.components.base import BASE_DIR
from config.components.enterprise import detect_enterprise_footprint, require_enterprise_license_management

install_apps = os.getenv("INSTALL_APPS", "")

# 企业版：检测 enterprise footprint，拒绝无 license_mgmt 时启动，按需注入显式列表
_base_dir = Path(BASE_DIR)
require_enterprise_license_management(_base_dir)
_enterprise_status = detect_enterprise_footprint(_base_dir)

if install_apps:
    # Normalise the explicit list, then gate license_mgmt on enterprise status.
    _apps_set = {a.strip() for a in install_apps.split(",") if a.strip()}
    if _enterprise_status.should_enable_license_mgmt:
        _apps_set.add("license_mgmt")
    else:
        # Block any explicit attempt to load license_mgmt without enterprise footprint.
        _apps_set.discard("license_mgmt")
    install_apps = ",".join(_apps_set)

for app in os.listdir(os.path.join(_base_dir, "apps")):
    # In auto-discovery mode, gate license_mgmt on enterprise status as well.
    if app == "license_mgmt" and not _enterprise_status.should_enable_license_mgmt:
        continue
    if install_apps and app not in install_apps.split(","):
        continue
    if app.endswith(".py") or app.startswith("__"):
        continue
    if os.path.exists(os.path.join(_base_dir, "apps", app, "config.py")):
        try:
            __module = __import__(f"apps.{app}.config", globals(), locals(), ["*"])
        except ImportError as e:  # noqa
            print(e)
        else:
            for _setting in dir(__module):
                if _setting == _setting.upper():
                    value = getattr(__module, _setting)
                    if isinstance(value, dict):
                        locals().setdefault(_setting, {}).update(value)
                    else:
                        locals()[_setting] = getattr(__module, _setting)
try:
    from local_settings import *  # noqa
except ImportError:
    pass
