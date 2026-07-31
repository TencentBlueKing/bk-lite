CATALOG_RECONCILE_HEALTH_KEY = "apm:catalog:reconcile:health"


def pending_catalog_health() -> dict[str, str]:
    return {"status": "pending"}
