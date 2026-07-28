"""Canvas Share session 域 NetworkTopology runtime 校验。

Phase B-1：仅 metric_values / link_runtime。
禁止 body 指定 topology_id；node/link 必须属于 session 绑定画布的 view_sets。
"""

from __future__ import annotations

from typing import Any

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.operation_analysis.services.network_topology.runtime import _node_ref_from_view_set

_FORBIDDEN_BODY_KEYS = frozenset(
    {
        "topology_id",
        "canvas_id",
        "network_topology_id",
        "token",
        "base_url",
        "decrypt_token",
    }
)

_NODE_REF_KEYS = frozenset(
    {
        "bk_obj_id",
        "bk_inst_id",
        "network_collect_task_id",
        "network_collect_instance_id",
        "plugin_group_id",
        "plugin_template_id",
    }
)

_METRIC_REF_KEYS = frozenset({"metric_field", "result_table_id"})


class ShareNetworkTopologyRuntimeDenied(PermissionDenied):
    """请求的 node/link 不属于分享画布 view_sets。"""

    default_detail = "无权访问当前网络拓扑运行态"
    default_code = "share_nt_runtime_denied"


def reject_forbidden_topology_body_keys(data: Any) -> None:
    if not isinstance(data, dict):
        raise ValidationError({"detail": "请求体必须是对象"})
    hit = _FORBIDDEN_BODY_KEYS.intersection(data.keys())
    if hit:
        raise ValidationError({"detail": f"禁止在分享请求中指定: {', '.join(sorted(hit))}"})


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_node_ref(ref: dict[str, Any]) -> tuple:
    return (
        str(ref.get("bk_obj_id") or ""),
        _as_int(ref.get("bk_inst_id")),
        _as_int(ref.get("network_collect_task_id")),
        _as_int(ref.get("network_collect_instance_id")),
        _as_int(ref.get("plugin_group_id")),
        str(ref.get("plugin_template_id") or "0"),
    )


def _view_sets_nodes(view_sets: Any) -> list[dict[str, Any]]:
    if not isinstance(view_sets, dict):
        return []
    nodes = view_sets.get("nodes") or []
    return [node for node in nodes if isinstance(node, dict)]


def _view_sets_links(view_sets: Any) -> list[dict[str, Any]]:
    if not isinstance(view_sets, dict):
        return []
    links = view_sets.get("links") or []
    return [link for link in links if isinstance(link, dict)]


def _find_node_by_ref(view_sets: Any, node_ref: dict[str, Any]) -> dict[str, Any] | None:
    target = _normalize_node_ref(node_ref)
    for node in _view_sets_nodes(view_sets):
        if _normalize_node_ref(_node_ref_from_view_set(node)) == target:
            return node
        # 前端 node_ref 可能省略 plugin_group_id；再按核心字段兜底匹配。
        loose = (
            str(node.get("bk_obj_id") or ""),
            _as_int(node.get("bk_inst_id")),
            _as_int(node.get("network_collect_task_id")),
            _as_int(node.get("network_collect_instance_id")),
            str(node.get("plugin_template_id") or "0"),
        )
        request_loose = (
            str(node_ref.get("bk_obj_id") or ""),
            _as_int(node_ref.get("bk_inst_id")),
            _as_int(node_ref.get("network_collect_task_id")),
            _as_int(node_ref.get("network_collect_instance_id")),
            str(node_ref.get("plugin_template_id") or "0"),
        )
        if loose == request_loose:
            return node
    return None


_AGGREGATE_TYPES = frozenset({"sum", "max", "min", "mean", "last"})


def _find_stored_metric(node: dict[str, Any], metric_ref: dict[str, Any]) -> dict[str, Any] | None:
    field = metric_ref.get("metric_field")
    table = metric_ref.get("result_table_id")
    if not field or not table:
        return None
    for metric in node.get("metrics") or []:
        if not isinstance(metric, dict):
            continue
        if metric.get("metric_field") == field and metric.get("result_table_id") == table:
            return metric
    return None


def _stored_metric_query_semantics(metric: dict[str, Any]) -> dict[str, Any]:
    """与 NetworkTopologyRuntimeService._build_metric_requests 对齐：只用画布已存配置。"""
    dimensions = metric.get("dimensions") if isinstance(metric.get("dimensions"), dict) else {}
    condition_filter = (
        metric.get("condition_filter") if isinstance(metric.get("condition_filter"), list) else []
    )
    raw_mode = metric.get("display_mode")
    if raw_mode in ("aggregate", "dimension"):
        display_mode = raw_mode
    else:
        display_mode = "dimension" if condition_filter or dimensions else "aggregate"
    raw_aggregate = metric.get("aggregate_type")
    aggregate_type = raw_aggregate if raw_aggregate in _AGGREGATE_TYPES else "sum"
    return {
        "dimensions": dimensions,
        "condition_filter": condition_filter,
        "display_mode": display_mode,
        "aggregate_type": aggregate_type,
    }


def _validate_node_ref_shape(node_ref: Any) -> dict[str, Any]:
    if not isinstance(node_ref, dict) or not node_ref:
        raise ValidationError({"node_ref": ["node_ref 必填且必须是对象"]})
    unknown = set(node_ref.keys()) - _NODE_REF_KEYS
    if unknown:
        raise ValidationError({"node_ref": [f"包含未声明字段: {', '.join(sorted(unknown))}"]})
    if "bk_obj_id" not in node_ref or "bk_inst_id" not in node_ref:
        raise ValidationError({"node_ref": ["缺少 bk_obj_id / bk_inst_id"]})
    return node_ref


def _validate_metric_ref_shape(metric_ref: Any) -> dict[str, Any]:
    if not isinstance(metric_ref, dict) or not metric_ref:
        raise ValidationError({"metric_ref": ["metric_ref 必填且必须是对象"]})
    unknown = set(metric_ref.keys()) - _METRIC_REF_KEYS
    if unknown:
        raise ValidationError({"metric_ref": [f"包含未声明字段: {', '.join(sorted(unknown))}"]})
    if not metric_ref.get("metric_field") or not metric_ref.get("result_table_id"):
        raise ValidationError({"metric_ref": ["metric_field / result_table_id 必填"]})
    return metric_ref


def validate_share_metric_values(*, view_sets: Any, items: Any) -> list[dict[str, Any]]:
    """校验 metric_values items，返回可转发的规范化列表。

    查询语义（dimensions / condition_filter / display_mode / aggregate_type）
    一律取自 view_sets 已存 metric，忽略客户端覆盖，防止分享边界内扩大 WeOps 查询面。
    """
    if not isinstance(items, list):
        raise ValidationError({"items": ["items 必须是数组"]})

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValidationError({"items": [f"items[{index}] 必须是对象"]})
        request_id = raw.get("request_id")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValidationError({"items": [f"items[{index}].request_id 必填"]})

        node_ref = _validate_node_ref_shape(raw.get("node_ref"))
        metric_ref = _validate_metric_ref_shape(raw.get("metric_ref"))

        node = _find_node_by_ref(view_sets, node_ref)
        if node is None:
            raise ShareNetworkTopologyRuntimeDenied("node_ref 不属于当前分享画布")
        stored_metric = _find_stored_metric(node, metric_ref)
        if stored_metric is None:
            raise ShareNetworkTopologyRuntimeDenied("metric_ref 不属于当前分享画布节点")

        item: dict[str, Any] = {
            "request_id": request_id.strip(),
            "node_ref": _node_ref_from_view_set(node),
            "metric_ref": {
                "metric_field": stored_metric.get("metric_field"),
                "result_table_id": stored_metric.get("result_table_id"),
            },
            **_stored_metric_query_semantics(stored_metric),
        }
        normalized.append(item)
    return normalized


def _port_pairs_fingerprint(link: dict[str, Any]) -> list[tuple]:
    pairs = link.get("port_pairs") or []
    fingerprints = []
    for pair in pairs:
        if not isinstance(pair, dict):
            continue
        source = pair.get("source_interface") or {}
        target = pair.get("target_interface") or {}
        fingerprints.append(
            (
                _as_int(source.get("bk_inst_id")),
                str(source.get("interface_name") or ""),
                _as_int(target.get("bk_inst_id")),
                str(target.get("interface_name") or ""),
            )
        )
    return fingerprints


def validate_share_link_runtime(
    *,
    view_sets: Any,
    link_payload: Any,
    nodes_payload: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """校验 link_runtime，返回 (canonical_link, canonical_endpoint_nodes)。"""
    if not isinstance(link_payload, dict) or not link_payload:
        raise ValidationError({"link": ["link 必须是对象"]})
    if nodes_payload is not None and not isinstance(nodes_payload, list):
        raise ValidationError({"nodes": ["nodes 必须是数组"]})

    link_id = link_payload.get("id")
    if not isinstance(link_id, str) or not link_id.strip():
        raise ValidationError({"link": ["link.id 必填"]})

    stored = next((item for item in _view_sets_links(view_sets) if item.get("id") == link_id), None)
    if stored is None:
        raise ShareNetworkTopologyRuntimeDenied("link 不属于当前分享画布")

    if link_payload.get("source_node_id") != stored.get("source_node_id") or link_payload.get(
        "target_node_id"
    ) != stored.get("target_node_id"):
        raise ShareNetworkTopologyRuntimeDenied("link 端点与分享画布不一致")

    if _port_pairs_fingerprint(link_payload) != _port_pairs_fingerprint(stored):
        raise ShareNetworkTopologyRuntimeDenied("link 端口对与分享画布不一致")

    nodes_by_id = {node.get("id"): node for node in _view_sets_nodes(view_sets)}
    endpoint_ids = {stored.get("source_node_id"), stored.get("target_node_id")}
    endpoint_ids.discard(None)

    if nodes_payload is None:
        nodes_payload = [nodes_by_id[node_id] for node_id in endpoint_ids if node_id in nodes_by_id]
    else:
        for index, node in enumerate(nodes_payload):
            if not isinstance(node, dict):
                raise ValidationError({"nodes": [f"nodes[{index}] 必须是对象"]})
            node_id = node.get("id")
            if node_id not in nodes_by_id:
                raise ShareNetworkTopologyRuntimeDenied("nodes 不属于当前分享画布")
            if node_id not in endpoint_ids:
                raise ShareNetworkTopologyRuntimeDenied("nodes 超出当前 link 端点")
            stored_node = nodes_by_id[node_id]
            if _normalize_node_ref(_node_ref_from_view_set(node)) != _normalize_node_ref(
                _node_ref_from_view_set(stored_node)
            ):
                raise ShareNetworkTopologyRuntimeDenied("node_ref 与分享画布不一致")

    canonical_nodes = [nodes_by_id[node_id] for node_id in endpoint_ids if node_id in nodes_by_id]
    return stored, canonical_nodes
