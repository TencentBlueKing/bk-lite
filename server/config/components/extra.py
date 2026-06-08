import os
from pathlib import Path

from config.components.enterprise import detect_enterprise_footprint, require_enterprise_license_management

install_apps = os.getenv("INSTALL_APPS", "")

# 企业版：检测 enterprise footprint，拒绝无 license_mgmt 时启动，按需注入显式列表
require_enterprise_license_management(Path.cwd())
_enterprise_status = detect_enterprise_footprint(Path.cwd())
if _enterprise_status.should_enable_license_mgmt:
    if install_apps:
        apps_set = {a.strip() for a in install_apps.split(",") if a.strip()}
        apps_set.add("license_mgmt")
        install_apps = ",".join(apps_set)

for app in os.listdir("apps"):
    if install_apps and app not in install_apps.split(","):
        continue
    if app.endswith(".py") or app.startswith("__"):
        continue
    if os.path.exists(f"apps/{app}/config.py"):
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
