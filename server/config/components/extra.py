import os

install_apps = os.getenv("INSTALL_APPS", "")

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
