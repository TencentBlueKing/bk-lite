import os

for app in os.listdir("apps"):
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
                    locals()[_setting] = getattr(__module, _setting)
try:
    from local_settings import *  # noqa
except ImportError:
    pass
