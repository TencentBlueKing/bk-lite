try:
    from apps.cmdb.enterprise.serializers import *  # noqa
except ModuleNotFoundError as exc:
    if exc.name not in {"apps.cmdb.enterprise", "apps.cmdb.enterprise.serializers"}:
        raise
