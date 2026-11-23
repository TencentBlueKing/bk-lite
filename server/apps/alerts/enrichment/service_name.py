"""把 CMDB 应用名称写入事件 service。命中才替换上报值。"""

MAX_SERVICE_LENGTH = 200

_FAILURE_STATUSES = {
    "provider_failed",
    "circuit_open",
    "budget_exhausted",
    "provider_saturated",
}


def _stripped(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _overlay_present(records) -> bool:
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for key in record:
            if isinstance(key, str) and (key.startswith("application.") or key.startswith("system.")):
                return True
    return False


def _smallest_application_record(records) -> dict:
    ranked = []
    for index, record in enumerate(records or []):
        if not isinstance(record, dict):
            continue
        identity = _stripped(record.get("_cmdb_root_uuid"))
        ranked.append((identity == "", identity, index, record))
    if not ranked:
        return {}
    ranked.sort()
    return ranked[0][3]


def choose_cmdb_service_name(records) -> str:
    """root_uuid 最小的应用名，应用名为空时用该条上的系统名。超长视为未命中。"""
    record = _smallest_application_record(records)
    if not record:
        return ""
    name = _stripped(record.get("application.inst_name")) or _stripped(record.get("system.inst_name"))
    if not name or len(name) > MAX_SERVICE_LENGTH:
        return ""
    return name


def remember_cmdb_service(sink, rule, records, status, events) -> None:
    if getattr(rule, "provider_type", "") != "cmdb":
        return
    if status in _FAILURE_STATUSES:
        return
    if not _overlay_present(records):
        return
    name = choose_cmdb_service_name(records)
    if not name:
        return
    namespace = getattr(rule, "resolved_namespace", "") or "cmdb"
    for event in events:
        sink.setdefault(id(event), (namespace, name))


def apply_cmdb_service(events, sink) -> None:
    for event in events:
        chosen = sink.get(id(event))
        if not chosen:
            continue
        namespace, name = chosen
        event["service"] = name
        enrichment = event.setdefault("enrichment", {})
        if not isinstance(enrichment, dict):
            continue
        bucket = enrichment.get(namespace)
        if bucket is None:
            enrichment[namespace] = {"service": name}
            continue
        if isinstance(bucket, dict):
            bucket["service"] = name
