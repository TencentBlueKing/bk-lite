"""按可配置 CMDB 关联，把对端实例上的活跃监控告警汇总到源模型实例。

告警口径是授权主机上 status=new 的监控告警。没有关联主机的源实例算作无关联告警。
调用方负责权限、分页和查数；这里只做纯汇总，供汇总和 TOP 复用。
"""

from __future__ import annotations

from typing import Any

RELATION_ALERT_VIEWS = frozenset({"summary", "top"})
DEFAULT_TOP_LIMIT = 5
MAX_TOP_LIMIT = 50


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def peers_by_source_from_edges(
    edges: list[dict[str, Any]] | None,
    source_uuids: list[str],
    source_model_id: str,
    peer_model_id: str,
) -> dict[str, list[str]]:
    """每条源实例保留自己的对端，同一对端可同时属于多个源。"""
    source_set = set(source_uuids)
    peers_by_source: dict[str, list[str]] = {uuid: [] for uuid in source_uuids}
    seen_by_source: dict[str, set[str]] = {uuid: set() for uuid in source_uuids}
    for edge in edges or []:
        if not isinstance(edge, dict):
            continue
        src_model = _text(edge.get("src_model_id"))
        dst_model = _text(edge.get("dst_model_id"))
        src_uuid = _text(edge.get("src_inst_uuid"))
        dst_uuid = _text(edge.get("dst_inst_uuid"))
        source_uuid = ""
        peer_uuid = ""
        if src_uuid in source_set and src_model == source_model_id and dst_model == peer_model_id:
            source_uuid, peer_uuid = src_uuid, dst_uuid
        elif dst_uuid in source_set and dst_model == source_model_id and src_model == peer_model_id:
            source_uuid, peer_uuid = dst_uuid, src_uuid
        if not source_uuid or not peer_uuid:
            continue
        seen_peers = seen_by_source.get(source_uuid)
        if seen_peers is None or peer_uuid in seen_peers:
            continue
        seen_peers.add(peer_uuid)
        peers_by_source[source_uuid].append(peer_uuid)
    return peers_by_source


def _entity_rows(
    entities: list[dict[str, Any]] | None,
    peers_by_source: dict[str, list[str]],
    alert_count_by_peer: dict[str, int] | None,
) -> list[dict[str, Any]]:
    counts = alert_count_by_peer or {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entity in entities or []:
        if not isinstance(entity, dict):
            continue
        inst_uuid = _text(entity.get("inst_uuid"))
        if not inst_uuid or inst_uuid in seen:
            continue
        seen.add(inst_uuid)
        peers = peers_by_source.get(inst_uuid) or []
        alert_count = sum(int(counts.get(peer) or 0) for peer in peers)
        inst_name = _text(entity.get("inst_name")) or inst_uuid
        rows.append(
            {
                "inst_uuid": inst_uuid,
                "name": inst_name,
                "host_count": len(peers),
                "alert_count": alert_count,
                "value": alert_count,
            }
        )
    return rows


def _percent_text(rate: float) -> str:
    return f"{rate:.1f}%"


def instance_share_pair(part: int, total: int) -> tuple[str, str]:
    """占比与补集都保留一位小数，两者相加为 100.0%；没有分母时都是 0.0%。"""
    if total <= 0:
        return "0.0%", "0.0%"
    rate = round((part / total) * 100, 1)
    return _percent_text(rate), _percent_text(round(100 - rate, 1))


def alert_share_text(count: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return _percent_text(round((count / total) * 100, 1))


def empty_relation_alert_payload(view: str) -> dict[str, Any] | list[dict[str, Any]]:
    if view == "top":
        return []
    with_share, without_share = instance_share_pair(0, 0)
    return {
        "total_count": 0,
        "with_alert_count": 0,
        "without_alert_count": 0,
        "with_alert_share": with_share,
        "without_alert_share": without_share,
    }


def normalize_relation_alert_limit(value: Any, *, default: int = DEFAULT_TOP_LIMIT) -> int:
    if value in (None, ""):
        return default
    try:
        limit = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit 必须是正整数") from exc
    if limit <= 0:
        raise ValueError("limit 必须是正整数")
    return min(limit, MAX_TOP_LIMIT)


def build_relation_alert_view(
    *,
    entities: list[dict[str, Any]] | None,
    edges: list[dict[str, Any]] | None,
    alert_count_by_peer: dict[str, int] | None,
    source_model_id: str,
    peer_model_id: str,
    view: str,
    limit: int = DEFAULT_TOP_LIMIT,
) -> dict[str, Any] | list[dict[str, Any]]:
    """summary / top。无主机关联或对端没有活跃告警的源实例计入无关联告警。"""
    source_ids = []
    seen: set[str] = set()
    for entity in entities or []:
        if not isinstance(entity, dict):
            continue
        inst_uuid = _text(entity.get("inst_uuid"))
        if not inst_uuid or inst_uuid in seen:
            continue
        seen.add(inst_uuid)
        source_ids.append(inst_uuid)
    peers_by_source = peers_by_source_from_edges(edges, source_ids, source_model_id, peer_model_id)
    rows = _entity_rows(entities, peers_by_source, alert_count_by_peer)
    with_alert = [row for row in rows if row["alert_count"] > 0]
    if view == "top":
        ranked = sorted(with_alert, key=lambda item: (-item["alert_count"], item["name"], item["inst_uuid"]))
        alert_total = sum(int(item["alert_count"]) for item in rows)
        return [
            {
                "name": item["name"],
                "value": item["value"],
                "inst_uuid": item["inst_uuid"],
                "host_count": item["host_count"],
                "alert_count": item["alert_count"],
                "share": alert_share_text(int(item["alert_count"]), alert_total),
            }
            for item in ranked[:limit]
        ]
    total_count = len(rows)
    with_alert_count = len(with_alert)
    with_share, without_share = instance_share_pair(with_alert_count, total_count)
    return {
        "total_count": total_count,
        "with_alert_count": with_alert_count,
        "without_alert_count": total_count - with_alert_count,
        "with_alert_share": with_share,
        "without_alert_share": without_share,
    }
