try:
    from apps.cmdb.enterprise.services.custom_reporting_ingest_service import *  # noqa
except ModuleNotFoundError as exc:
    if exc.name not in {
        "apps.cmdb.enterprise",
        "apps.cmdb.enterprise.services",
        "apps.cmdb.enterprise.services.custom_reporting_ingest_service",
    }:
        raise
