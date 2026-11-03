"""批量判断监控实例是否已存在（扫描清单纳管列）。"""

from django.db.models import Q

from apps.monitor.models.monitor_object import MonitorInstance

EXIST_LIMIT = 200


def _bounded_texts(values):
    if values is None:
        return []
    if not isinstance(values, list) or len(values) > EXIST_LIMIT:
        return None
    unique = []
    seen = set()
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _org_ids(values):
    if not isinstance(values, list) or len(values) > EXIST_LIMIT:
        return []
    unique = []
    seen = set()
    for item in values:
        try:
            org_id = int(item)
        except (TypeError, ValueError):
            continue
        if org_id in seen:
            continue
        seen.add(org_id)
        unique.append(org_id)
    return unique


def list_existing_monitor_instances(*, cmdb_ids=None, ips=None, allowed_org_ids=None) -> dict:
    """按 cmdb_id / IP 批量返回当前组织下未删除的监控实例。

    空组织 fail-closed。单次最多 200 个 cmdb_id 与 200 个 IP。
    """
    bounded_cmdb = _bounded_texts(cmdb_ids)
    bounded_ips = _bounded_texts(ips)
    if bounded_cmdb is None or bounded_ips is None:
        return {"result": False, "data": {"cmdb_ids": [], "ips": []}, "message": "invalid"}

    org_ids = _org_ids(allowed_org_ids)
    if not org_ids or (not bounded_cmdb and not bounded_ips):
        return {"result": True, "data": {"cmdb_ids": [], "ips": []}, "message": ""}

    query = Q()
    if bounded_cmdb:
        query |= Q(cmdb_id__in=bounded_cmdb)
    if bounded_ips:
        query |= Q(ip__in=bounded_ips)
    rows = (
        MonitorInstance.objects.filter(is_deleted=False, monitorinstanceorganization__organization__in=org_ids)
        .filter(query)
        .values_list("cmdb_id", "ip")
        .distinct()
    )
    wanted_cmdb = set(bounded_cmdb)
    wanted_ips = set(bounded_ips)
    found_cmdb = set()
    found_ips = set()
    for cmdb_id, ip in rows:
        cid = str(cmdb_id or "").strip()
        if cid and cid in wanted_cmdb:
            found_cmdb.add(cid)
        ip_text = str(ip or "").strip()
        if ip_text and ip_text in wanted_ips:
            found_ips.add(ip_text)
    return {
        "result": True,
        "message": "",
        "data": {
            "cmdb_ids": [item for item in bounded_cmdb if item in found_cmdb],
            "ips": [item for item in bounded_ips if item in found_ips],
        },
    }
