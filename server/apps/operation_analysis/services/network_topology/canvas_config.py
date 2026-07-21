# -*- coding: utf-8 -*-
"""
Canvas config (view_sets JSON) read/write helpers for ``NetworkTopology``.

Responsibilities:

* :func:`dump` — return the persisted view_sets as a defensive copy.
* :func:`replace` — overwrite the canvas JSON atomically after running the
  full structural validator (:meth:`NetworkTopology.clean_view_sets`).
* :func:`cascade_remove_node` / :func:`cascade_remove_link` — application-
  level cascade helpers invoked by the view layer when a node or link is
  deleted (design.md §6.5: cascading happens in the application layer since
  the table is no longer relational).

These helpers do NOT call WeOps themselves — they only manipulate the
JSON persisted on the canvas. Use
:class:`apps.operation_analysis.services.network_topology.runtime.NetworkTopologyRuntimeService`
for run-state queries.
"""

from __future__ import annotations

import copy
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError

# Use a single alias to keep the call sites uniform. We want callers
# (serializer and model) to be able to catch the same exception the
# tests are asserting on.
ValidationError = DjangoValidationError

INTERFACE_METRIC_FIELDS = {
    "ifInOctets_5min",
    "ifOutOctets_5min",
    "ifOutDiscards_5min",
    "ifInDiscards_5min",
    "ifInErrors_5min",
    "ifOutErrors_5min",
    "ifHighSpeed",
}


def dump(topology) -> dict[str, Any]:
    """Return a defensive copy of the canvas' view_sets.

    Older callers might still send ``view_sets=null`` or an empty dict;
    normalize to ``{"nodes": [], "links": []}`` for forward compatibility.
    """
    payload = topology.view_sets or {}
    if not isinstance(payload, dict):
        payload = {}
    nodes = payload.get("nodes") or []
    links = payload.get("links") or []
    return {"nodes": list(nodes), "links": list(links)}


def replace(topology, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Persist ``view_sets`` after running full structural validation.

    The persisted JSON is normalized to ``{"nodes": [...], "links": [...]}``.
    Raises :class:`rest_framework.exceptions.ValidationError` on any
    structural problem (so the view layer can return a 400 with the per-
    field messages).
    """
    normalized = _validate_payload(payload)
    topology.view_sets = normalized
    topology.save(update_fields=["view_sets", "updated_at"])
    return dump(topology)


def cascade_remove_node(topology, node_id: str) -> dict[str, Any]:
    """Remove the node identified by ``node_id`` and any links referencing it.

    Returns the updated view_sets. Idempotent: requesting removal of a
    missing node is a no-op.
    """
    payload = dump(topology)
    nodes = [n for n in payload["nodes"] if n.get("id") != node_id]
    links = [link for link in payload["links"] if link.get("source_node_id") != node_id and link.get("target_node_id") != node_id]
    new_payload = {"nodes": nodes, "links": links}
    topology.view_sets = new_payload
    topology.save(update_fields=["view_sets", "updated_at"])
    return dump(topology)


def cascade_remove_link(topology, link_id: str) -> dict[str, Any]:
    """Remove the link identified by ``link_id`` (no associated rows anymore)."""
    payload = dump(topology)
    links = [link for link in payload["links"] if link.get("id") != link_id]
    new_payload = {"nodes": payload["nodes"], "links": links}
    topology.view_sets = new_payload
    topology.save(update_fields=["view_sets", "updated_at"])
    return dump(topology)


# --------------------------------------------------------------------------- #
# Internal helpers                                                             #
# --------------------------------------------------------------------------- #


def _validate_single_node(
    raw_node: Any,
    index: int,
    seen_node_ids: set[str],
    seen_asset_keys: set[tuple[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate one node entry. Returns ``(node_or_none, errors)``."""
    errors: list[str] = []
    if not isinstance(raw_node, dict):
        errors.append(f"节点 #{index} 必须是对象")
        return None, errors
    node_id = raw_node.get("id")
    if not node_id or not isinstance(node_id, str):
        errors.append(f"节点 #{index} 缺少 id 字段")
        return None, errors
    if node_id in seen_node_ids:
        errors.append(f"节点 id {node_id!r} 重复")
        return None, errors
    seen_node_ids.add(node_id)

    bk_obj_id = raw_node.get("bk_obj_id")
    bk_inst_id = raw_node.get("bk_inst_id")
    if not bk_obj_id or bk_inst_id in (None, ""):
        errors.append(f"节点 {node_id} 缺少 bk_obj_id 或 bk_inst_id")
        return None, errors
    asset_key = (bk_obj_id, bk_inst_id)
    if asset_key in seen_asset_keys:
        errors.append(f"节点 {node_id} 与画布中已有节点 ({bk_obj_id}, {bk_inst_id}) 重复")
        return None, errors
    seen_asset_keys.add(asset_key)

    metrics = raw_node.get("metrics") or []
    if not isinstance(metrics, list):
        errors.append(f"节点 {node_id} 的 metrics 必须是数组")
    for m_index, metric in enumerate(metrics):
        if not isinstance(metric, dict):
            errors.append(f"节点 {node_id} 指标 #{m_index} 必须是对象")
            continue
        if not metric.get("metric_field"):
            errors.append(f"节点 {node_id} 指标 #{m_index} 缺少 metric_field")
        if not metric.get("result_table_id"):
            errors.append(f"节点 {node_id} 指标 #{m_index} 缺少 result_table_id")
        thresholds = metric.get("thresholds") or []
        if not isinstance(thresholds, list):
            errors.append(f"节点 {node_id} 指标 #{m_index} 的 thresholds 必须是数组")
            continue
        for t_index, threshold in enumerate(thresholds):
            if not isinstance(threshold, dict):
                errors.append(f"节点 {node_id} 指标 #{m_index} 阈值 #{t_index} 必须是对象")
                continue
            if "value" not in threshold:
                errors.append(f"节点 {node_id} 指标 #{m_index} 阈值 #{t_index} 缺少 value")
            if not threshold.get("color"):
                errors.append(f"节点 {node_id} 指标 #{m_index} 阈值 #{t_index} 缺少 color")
    return raw_node, errors


def _validate_single_link(
    raw_link: Any,
    index: int,
    node_ids: dict[str, dict[str, Any]],
    seen_link_ids: set[str],
) -> list[str]:
    """Validate one link entry. Returns error strings (empty = OK)."""
    errors: list[str] = []
    if not isinstance(raw_link, dict):
        errors.append(f"连线 #{index} 必须是对象")
        return errors
    link_id = raw_link.get("id") or f"link-{index}"
    if link_id in seen_link_ids:
        errors.append(f"连线 id {link_id!r} 重复")
        return errors
    seen_link_ids.add(link_id)
    source_node_id = raw_link.get("source_node_id")
    target_node_id = raw_link.get("target_node_id")
    if source_node_id not in node_ids:
        errors.append(f"连线 {link_id} 的 source_node_id {source_node_id!r} 不在画布中")
    if target_node_id not in node_ids:
        errors.append(f"连线 {link_id} 的 target_node_id {target_node_id!r} 不在画布中")
    for field in ("source_port_id", "target_port_id"):
        if raw_link.get(field) is not None and not isinstance(raw_link.get(field), str):
            errors.append(f"连线 {link_id} 的 {field} 必须是字符串")
    interface_metrics = raw_link.get("interface_metrics") or []
    if not isinstance(interface_metrics, list):
        errors.append(f"连线 {link_id} 的 interface_metrics 必须是数组")
    else:
        for metric_index, metric_field in enumerate(interface_metrics):
            if metric_field not in INTERFACE_METRIC_FIELDS:
                errors.append(f"连线 {link_id} 接口指标 #{metric_index} 不支持: {metric_field}")
    port_pairs = raw_link.get("port_pairs") or []
    if not isinstance(port_pairs, list):
        errors.append(f"连线 {link_id} 的 port_pairs 必须是数组")
        return errors
    if not raw_link.get("is_draft") and len(port_pairs) == 0:
        errors.append(f"连线 {link_id} 至少需要 1 对端口")
    for pair_index, pair in enumerate(port_pairs):
        if not isinstance(pair, dict):
            errors.append(f"连线 {link_id} 端口对 #{pair_index} 必须是对象")
            continue
        source_iface = pair.get("source_interface")
        target_iface = pair.get("target_interface")
        if not isinstance(source_iface, dict) or not source_iface.get("bk_inst_id"):
            errors.append(f"连线 {link_id} 端口对 #{pair_index} 缺少源接口 bk_inst_id")
        if not isinstance(target_iface, dict) or not target_iface.get("bk_inst_id"):
            errors.append(f"连线 {link_id} 端口对 #{pair_index} 缺少目标接口 bk_inst_id")
    return errors


def _validate_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Apply :meth:`NetworkTopology.clean_view_sets` semantics without a DB row.

    We don't want to round-trip through ``topology.clean_view_sets`` because
    serializers call this in :meth:`Serializer.validate` before the instance
    exists. We mirror the validation rule set literally.
    """
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValidationError({"view_sets": ["view_sets 必须是 JSON 对象"]})

    nodes = payload.get("nodes") or []
    links = payload.get("links") or []
    if not isinstance(nodes, list):
        raise ValidationError({"view_sets": ["nodes 必须是数组"]})
    if not isinstance(links, list):
        raise ValidationError({"view_sets": ["links 必须是数组"]})

    node_errors: list[str] = []
    link_errors: list[str] = []

    seen_node_ids: set[str] = set()
    seen_asset_keys: set[tuple[str, Any]] = set()
    seen_link_ids: set[str] = set()
    node_ids: dict[str, dict[str, Any]] = {}

    for index, raw_node in enumerate(nodes):
        node, errors = _validate_single_node(raw_node, index, seen_node_ids, seen_asset_keys)
        if errors:
            node_errors.extend(errors)
        if node is not None:
            node_ids[node["id"]] = node

    for index, raw_link in enumerate(links):
        link_errors.extend(_validate_single_link(raw_link, index, node_ids, seen_link_ids))

    detail: dict[str, list[str]] = {}
    if node_errors:
        detail["nodes"] = node_errors
    if link_errors:
        detail["links"] = link_errors

    if detail:
        # Django's ``ValidationError`` accepts a dict of per-field errors
        # and exposes them via ``message_dict``. DRF's ``ValidationError``
        # wraps the same payload so view-side ``raise_exception=True``
        # keeps working unchanged.
        raise ValidationError(detail)

    return {"nodes": copy.deepcopy(nodes), "links": copy.deepcopy(links)}
