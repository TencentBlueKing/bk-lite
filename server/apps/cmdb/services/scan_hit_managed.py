"""扫描命中对照当前 CMDB / 监控，批量标注是否已纳管。"""

from __future__ import annotations

from apps.cmdb.models.scan_model import SCAN_WRITE_DATABASE_TYPES, SCAN_WRITE_MIDDLEWARE_TYPES
from apps.core.logger import cmdb_logger as logger

NETWORK_MODELS = frozenset({"switch", "router", "firewall", "loadbalance"})
_ENTITY_FIELDS = [
    "inst_uuid",
    "model_id",
    "ip_addr",
    "ip",
    "host",
    "port",
    "monitor_id",
    "serial_number",
    "uuid",
    "cloud",
    "organization",
]
_LOOKUP_LIMIT = 2000


def _text(value) -> str:
    return str(value or "").strip()


def _org_ids(values) -> list[int]:
    unique = []
    seen = set()
    for item in values or []:
        try:
            org_id = int(item)
        except (TypeError, ValueError):
            continue
        if org_id in seen:
            continue
        seen.add(org_id)
        unique.append(org_id)
    return unique


def _unique(values: list[str]) -> list[str]:
    unique = []
    seen = set()
    for item in values:
        text = _text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _snapshot(hit) -> dict:
    snapshot = getattr(hit, "snapshot", None)
    return snapshot if isinstance(snapshot, dict) else {}


def entity_ip(entity: dict) -> str:
    return _text(entity.get("ip_addr") or entity.get("ip") or entity.get("host"))


def entity_port(entity: dict) -> int:
    try:
        return int(entity.get("port") or 0)
    except (TypeError, ValueError):
        return 0


def hit_family(hit) -> str:
    family_run = getattr(hit, "family_run", None)
    return _text(getattr(family_run, "model_id", "") or getattr(hit, "protocol", ""))


def hit_port(hit) -> int:
    try:
        port = int(getattr(hit, "port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    if port:
        return port
    try:
        return int(_snapshot(hit).get("port") or 0)
    except (TypeError, ValueError):
        return 0


def match_scan_hit_entity(hit, entities: list[dict]) -> dict | None:
    """用扫描身份键对当前图实例做匹配；命中本行 inst_uuid 优先。"""
    wanted_uuid = _text(getattr(hit, "inst_uuid", ""))
    if wanted_uuid:
        for entity in entities:
            if _text(entity.get("inst_uuid")) == wanted_uuid:
                return entity

    host = _text(getattr(hit, "host", ""))
    if not host:
        return None
    family = hit_family(hit)
    model = _text(getattr(hit, "cmdb_model_id", ""))
    port = hit_port(hit)
    snapshot = _snapshot(hit)
    same_ip = [entity for entity in entities if entity_ip(entity) == host]

    if family == "physcial_server" or model == "physcial_server":
        serial = _text(snapshot.get("serial_number"))
        hardware_uuid = _text(snapshot.get("uuid"))
        if serial:
            for entity in entities:
                if _text(entity.get("serial_number")) == serial:
                    return entity
        if hardware_uuid:
            for entity in entities:
                if _text(entity.get("uuid")) == hardware_uuid:
                    return entity
        return next((entity for entity in same_ip if _text(entity.get("model_id")) == "physcial_server"), None)

    if family == "host" or model == "host":
        return next((entity for entity in same_ip if _text(entity.get("model_id")) == "host"), None)

    if family == "network" or model in NETWORK_MODELS:
        if model in NETWORK_MODELS:
            return next((entity for entity in same_ip if _text(entity.get("model_id")) == model), None)
        return next((entity for entity in same_ip if _text(entity.get("model_id")) in NETWORK_MODELS), None)

    target = model or family
    if target in SCAN_WRITE_DATABASE_TYPES or target in SCAN_WRITE_MIDDLEWARE_TYPES:
        if not port:
            return None
        for entity in same_ip:
            if _text(entity.get("model_id")) != target:
                continue
            if entity_port(entity) != port:
                continue
            return entity
    return None


def _load_cmdb_entities(hits, org_ids: list[int]) -> list[dict]:
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient
    from apps.cmdb.services.instance import InstanceManage

    hosts = _unique([getattr(hit, "host", "") for hit in hits])
    uuids = _unique([getattr(hit, "inst_uuid", "") for hit in hits])
    entities: list[dict] = []
    if hosts and org_ids:
        params = [
            {"field": "ip_addr", "type": "str[]", "value": hosts},
            {"field": "organization", "type": "list_any[]", "value": org_ids},
        ]
        with GraphClient() as ag:
            rows, _ = ag.query_entity(
                INSTANCE,
                params,
                page={"skip": 0, "limit": min(max(len(hosts) * 8, 200), _LOOKUP_LIMIT)},
                include_count=False,
                fields=_ENTITY_FIELDS,
            )
        entities.extend(row for row in rows or [] if isinstance(row, dict))

    found = {_text(entity.get("inst_uuid")) for entity in entities}
    missing = [uuid for uuid in uuids if uuid not in found]
    if missing:
        extra = InstanceManage.query_entity_by_uuids(missing, fields=_ENTITY_FIELDS) or []
        entities.extend(row for row in extra if isinstance(row, dict))
    return entities


def _load_monitor_presence(cmdb_ids: list[str], ips: list[str], org_ids: list[int]) -> tuple[set[str], set[str]]:
    if not org_ids or (not cmdb_ids and not ips):
        return set(), set()
    from apps.rpc.monitor import Monitor

    payload = Monitor().instances_exist(cmdb_ids=cmdb_ids, ips=ips, allowed_org_ids=org_ids)
    if not isinstance(payload, dict) or not payload.get("result"):
        return set(), set()
    data = payload.get("data") or {}
    return set(_unique(data.get("cmdb_ids") or [])), set(_unique(data.get("ips") or []))


def annotate_scan_hits_managed(hits, execution=None):
    """给当前页命中挂 cmdb_managed / monitor_managed，供序列化读取。"""
    for hit in hits or []:
        hit.cmdb_managed = False
        hit.monitor_managed = False
    if not hits:
        return hits

    org_ids = _org_ids(getattr(getattr(execution, "task", None), "team", None))
    try:
        entities = _load_cmdb_entities(hits, org_ids)
    except Exception as exc:
        logger.warning(
            "event=scan_hit_cmdb_lookup_failed execution=%s failed_stage=%s error_type=%s hit_count=%s",
            getattr(execution, "id", ""),
            "query_entity",
            type(exc).__name__,
            len(hits),
        )
        entities = []

    matched: dict[int, dict] = {}
    remaining_cmdb: list[str] = []
    ips_without_ci: list[str] = []
    for hit in hits:
        entity = match_scan_hit_entity(hit, entities)
        if entity is None:
            host = _text(getattr(hit, "host", ""))
            if host:
                ips_without_ci.append(host)
            continue
        hit.cmdb_managed = True
        matched[hit.id] = entity
        if _text(entity.get("monitor_id")):
            hit.monitor_managed = True
            continue
        uuid = _text(entity.get("inst_uuid"))
        if uuid:
            remaining_cmdb.append(uuid)

    try:
        found_cmdb, found_ips = _load_monitor_presence(_unique(remaining_cmdb), _unique(ips_without_ci), org_ids)
    except Exception as exc:
        logger.warning(
            "event=scan_hit_monitor_lookup_failed execution=%s failed_stage=%s error_type=%s hit_count=%s",
            getattr(execution, "id", ""),
            "instances_exist",
            type(exc).__name__,
            len(hits),
        )
        found_cmdb, found_ips = set(), set()

    for hit in hits:
        if hit.monitor_managed:
            continue
        entity = matched.get(hit.id)
        if entity is not None:
            uuid = _text(entity.get("inst_uuid"))
            if uuid and uuid in found_cmdb:
                hit.monitor_managed = True
            continue
        if _text(getattr(hit, "host", "")) in found_ips:
            hit.monitor_managed = True
    return hits
