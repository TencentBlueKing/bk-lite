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
        "alert_count": 0,
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
    unique_peers = collect_peer_uuids(peers_by_source)
    counts = alert_count_by_peer or {}
    unique_alert_count = sum(int(counts.get(peer) or 0) for peer in unique_peers)
    return {
        "total_count": total_count,
        "with_alert_count": with_alert_count,
        "without_alert_count": total_count - with_alert_count,
        "alert_count": unique_alert_count,
        "with_alert_share": with_share,
        "without_alert_share": without_share,
    }


def collect_peer_uuids(peers_by_source: dict[str, list[str]]) -> list[str]:
    """按首次出现顺序收集去重后的对端 uuid。"""
    collected: list[str] = []
    seen: set[str] = set()
    for peers in peers_by_source.values():
        for peer in peers:
            if peer in seen:
                continue
            seen.add(peer)
            collected.append(peer)
    return collected


def normalize_model_asst_ids(value: Any) -> list[str]:
    """一个字符串保持一跳；字符串列表按顺序构成关联路径。"""
    if value in (None, ""):
        raise ValueError("模型关联不能为空")
    if isinstance(value, str):
        association_id = value.strip()
        if not association_id:
            raise ValueError("模型关联不能为空")
        if "," in association_id:
            parts = [part.strip() for part in association_id.split(",")]
            if any(not part for part in parts):
                raise ValueError("模型关联不能为空")
            return parts
        return [association_id]
    if isinstance(value, (list, tuple)):
        association_ids: list[str] = []
        for raw in value:
            if isinstance(raw, (list, tuple)):
                raise ValueError("模型关联路径格式不正确")
            association_id = str(raw or "").strip()
            if not association_id:
                raise ValueError("模型关联不能为空")
            association_ids.append(association_id)
        if not association_ids:
            raise ValueError("模型关联不能为空")
        return association_ids
    raise ValueError("模型关联路径格式不正确")


def compose_path_peers(
    hop_edges: list[list[dict[str, Any]] | None],
    source_uuids: list[str],
    model_ids: list[str],
) -> dict[str, list[str]]:
    """按关联路径把源实例展开到最终对象；同一最终对象在同一源下只保留一次。"""
    if len(model_ids) != len(hop_edges) + 1:
        raise ValueError("关联路径与模型列表不匹配")
    if not hop_edges:
        return {uuid: [] for uuid in source_uuids}

    current_ids = source_uuids
    current_model = model_ids[0]
    current_peers: dict[str, list[str]] | None = None
    for index, edges in enumerate(hop_edges):
        next_model = model_ids[index + 1]
        nxt = peers_by_source_from_edges(edges, current_ids, current_model, next_model)
        if current_peers is None:
            current_peers = {uuid: list(nxt.get(uuid) or []) for uuid in source_uuids}
        else:
            composed: dict[str, list[str]] = {uuid: [] for uuid in source_uuids}
            seen_by_source: dict[str, set[str]] = {uuid: set() for uuid in source_uuids}
            for source_uuid, mids in current_peers.items():
                collected = composed.setdefault(source_uuid, [])
                seen_finals = seen_by_source.setdefault(source_uuid, set())
                for mid in mids:
                    for final_uuid in nxt.get(mid) or []:
                        if final_uuid in seen_finals:
                            continue
                        seen_finals.add(final_uuid)
                        collected.append(final_uuid)
            current_peers = composed
        current_model = next_model
        current_ids = collect_peer_uuids(current_peers)
    return current_peers or {uuid: [] for uuid in source_uuids}


def compose_two_hop_peers(
    first_edges: list[dict[str, Any]] | None,
    second_edges: list[dict[str, Any]] | None,
    source_uuids: list[str],
    source_model_id: str,
    intermediate_model_id: str,
    final_model_id: str,
) -> dict[str, list[str]]:
    """源经中间模型再到最终对象；同一最终对象在同一源下只保留一次。"""
    return compose_path_peers(
        [first_edges, second_edges],
        source_uuids,
        [source_model_id, intermediate_model_id, final_model_id],
    )


def edges_from_peers(
    peers_by_source: dict[str, list[str]],
    source_model_id: str,
    peer_model_id: str,
) -> list[dict[str, Any]]:
    """把源到对端的映射展成 build_relation_alert_view 可用的单向边。"""
    edges: list[dict[str, Any]] = []
    for source_uuid, peers in peers_by_source.items():
        for peer_uuid in peers:
            edges.append(
                {
                    "src_model_id": source_model_id,
                    "dst_model_id": peer_model_id,
                    "src_inst_uuid": source_uuid,
                    "dst_inst_uuid": peer_uuid,
                }
            )
    return edges
