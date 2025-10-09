import sys

if not hasattr(sys, "argv"):
    sys.argv = [""]

DJANGO_CONF_MODULE = "config.default"

try:
    _module = __import__(DJANGO_CONF_MODULE, globals(), locals(), ["*"])
except ImportError as e:
    raise ImportError("Could not import config '{}' (Is it on sys.path?): {}".format(DJANGO_CONF_MODULE, e))

for _setting in dir(_module):
    if _setting == _setting.upper():
        locals()[_setting] = getattr(_module, _setting)

INSTALLED_APPS = locals()["INSTALLED_APPS"]
CELERY_IMPORTS = locals()["CELERY_IMPORTS"]
MIDDLEWARE = locals()["MIDDLEWARE"]

# 屏蔽 User.username 非唯一警告（auth.W004）
SILENCED_SYSTEM_CHECKS = ["auth.W004"]
