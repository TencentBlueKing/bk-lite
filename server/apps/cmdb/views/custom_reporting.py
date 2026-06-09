try:
    from apps.cmdb.enterprise.views import *  # noqa
except ModuleNotFoundError as exc:
    if exc.name not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.views"}:
        raise
