# -*- coding: utf-8 -*-
"""
Runtime aggregation for network topology canvases.

Provides:

* :func:`resolve_active_threshold` — pick the deepest-hit threshold for one
  metric (design.md §2.5 / §7.7).
* :func:`resolve_node_outer_color` — aggregate per-node color from the metric
  hits, picking the deepest numeric threshold level and breaking ties by metric order
  (design.md §2.5 / §7.7). Unknown gray (``NODE_OUTER_COLOR_UNKNOWN``) when
  there is no data.
* :func:`resolve_link_status` — ``oper_status_down_only`` aggregation for
  port-pairs: any ``down`` interface ⇒ ``critical``; all ``up`` ⇒
  ``normal``; otherwise ``unknown`` (design.md §9.1).
* :class:`NetworkTopologyRuntimeService` — fetch fresh runtime data from
  WeOps via :class:`WeOpsTopologyAdapter`, attach aggregated node/link
  status, and persist the short-TTL display cache.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.utils import timezone

from apps.operation_analysis.models.models import NODE_OUTER_COLOR_UNKNOWN  # noqa: F401 — kept for downstream re-use

if TYPE_CHECKING:
    # Imported only for type hints; the runtime value is passed in via
    # the ``adapter`` argument to keep this module off the weops_adapter
    # import path (avoids a circular import).
    from apps.operation_analysis.services.network_topology.weops_adapter import WeOpsTopologyAdapter

# --------------------------------------------------------------------------- #
# Pure functions — no DB / IO. Easy to test.                                  #
# --------------------------------------------------------------------------- #


def resolve_active_threshold(
    metric: dict[str, Any],
    runtime: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return ``{"level": idx, "color": str}`` for a metric's deepest-hit threshold.

    ``None`` when the metric has no current value, no thresholds, or the
    value is ``NaN``. Thresholds are evaluated by numeric value ascending,
    independent from the UI/config array order.

    Each threshold may carry a ``value`` (number) and ``color`` (string). We
    do NOT interpret a ``severity`` field; P0 trusts the user's color
    string as-is (design.md §2.5).
    """
    if not runtime:
        return None
    raw_value = runtime.get("value")
    if raw_value is None:
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN guard
        return None

    thresholds = metric.get("thresholds") or []
    if not thresholds:
        return None

    ordered_thresholds: list[tuple[float, int, dict[str, Any]]] = []
    for index, threshold in enumerate(thresholds):
        try:
            threshold_value = float(threshold.get("value"))
        except (TypeError, ValueError):
            continue
        ordered_thresholds.append((threshold_value, index, threshold))
    ordered_thresholds.sort(key=lambda item: (item[0], item[1]))
    if not ordered_thresholds:
        return None

    level: int | None = None
    for index, (threshold_value, _original_index, _threshold) in enumerate(ordered_thresholds):
        if value >= threshold_value:
            level = index
        else:
            break

    if level is None:
        # Below every threshold — use the smallest one as a baseline
        # (design.md §2.5 / spec "Metric value below all thresholds uses
        # baseline color").
        return {"level": 0, "color": ordered_thresholds[0][2].get("color")}

    chosen = ordered_thresholds[level][2]
    return {"level": level, "color": chosen.get("color")}


def resolve_node_outer_color(
    metrics: list[dict[str, Any]],
    runtime_metrics: list[dict[str, Any]],
) -> str | None:
    """Pick the deepest-hit metric's color (tie-breaker: first metric).

    Returns ``None`` when the node has no metrics, when no metric hits any
    threshold, or when metrics exist but no current value is available —
    callers interpret ``None`` as "use unknown gray".

    Matching is by ``(metric_field, result_table_id)`` to disambiguate same
    field name across result tables.
    """
    if not metrics:
        return None

    candidates: list[tuple[int, int, str]] = []
    for index, metric in enumerate(metrics):
        runtime = next(
            (
                item
                for item in runtime_metrics
                if item.get("metric_field") == metric.get("metric_field") and item.get("result_table_id") == metric.get("result_table_id")
            ),
            None,
        )
        hit = resolve_active_threshold(metric, runtime)
        if hit is None:
            continue
        candidates.append((index, hit["level"], hit["color"]))

    if not candidates:
        return None

    # Sort by deepest level first; tie-break by metric index.
    candidates.sort(key=lambda item: (-item[1], item[0]))
    return candidates[0][2]


def resolve_link_status(
    interface_items: list[dict[str, Any]],
) -> dict[str, str]:
    """``oper_status_down_only`` aggregation for a link's interfaces.

    Outcomes (design.md §9.1):

    * No interface items ⇒ ``unknown`` (no reference).
    * Any interface with ``oper_status == "down"`` ⇒ ``critical``.
    * All interfaces ``up`` with ``status == "ok"`` ⇒ ``normal``.
    * Else (``unknown`` / ``testing`` / missing data / error) ⇒ ``unknown``.
    """
    if not interface_items:
        return {"status": "unknown", "reason": "no_interface"}

    for item in interface_items:
        if item.get("oper_status") == "down":
            return {"status": "critical", "reason": "interface_down"}

    if all(item.get("oper_status") == "up" and item.get("status", "ok") == "ok" for item in interface_items):
        return {"status": "normal", "reason": "all_interface_up"}

    return {"status": "unknown", "reason": "interface_unknown"}


# --------------------------------------------------------------------------- #
# Runtime service                                                              #
# --------------------------------------------------------------------------- #


class NetworkTopologyRuntimeService:
    """Orchestrate run-state for a single canvas.

    Holds the cache TTL constant and exposes ``build_runtime`` /
    ``cache_payload`` / ``fresh_cached_payload``. WeOps calls go through
    :class:`WeOpsTopologyAdapter` so view-layer wiring is trivial.
    """

    CACHE_TTL_SECONDS = 60  # design.md §8 default refresh interval
    CACHE_GENERATED_AT_KEY = "_generated_at"
    INTERFACE_METRIC_FIELDS = {
        "ifInOctets_5min",
        "ifOutOctets_5min",
        "ifOutDiscards_5min",
        "ifInDiscards_5min",
        "ifInErrors_5min",
        "ifOutErrors_5min",
        "ifHighSpeed",
    }

    OPER_STATUS_NORMAL = "normal"
    OPER_STATUS_CRITICAL = "critical"
    OPER_STATUS_UNKNOWN = "unknown"

    # ------------------------------------------------------------------ #
    # Cache management                                                    #
    # ------------------------------------------------------------------ #
    @classmethod
    def cache_payload(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Stamp ``_generated_at`` then return the payload for storage."""
        stamped = dict(data or {})
        stamped[cls.CACHE_GENERATED_AT_KEY] = timezone.now().isoformat()
        return stamped

    @classmethod
    def fresh_cached_payload(cls, topology) -> dict[str, Any]:
        """Return the cached payload only if it is still inside the TTL window."""
        cached = topology.last_runtime_cache or {}
        generated_at = cached.get(cls.CACHE_GENERATED_AT_KEY)
        if not generated_at:
            return {}
        try:
            generated_time = timezone.datetime.fromisoformat(generated_at)
        except (TypeError, ValueError):
            return {}
        if timezone.is_naive(generated_time):
            generated_time = timezone.make_aware(generated_time, timezone.get_current_timezone())
        if timezone.now() - generated_time > timedelta(seconds=cls.CACHE_TTL_SECONDS):
            return {}
        return {key: value for key, value in cached.items() if key != cls.CACHE_GENERATED_AT_KEY}

    # ------------------------------------------------------------------ #
    # Run-state construction                                              #
    # ------------------------------------------------------------------ #
    @classmethod
    def build_runtime(cls, topology, adapter: WeOpsTopologyAdapter) -> dict[str, Any]:
        view_sets = topology.view_sets or {}
        nodes_payload = view_sets.get("nodes") or []
        links_payload = view_sets.get("links") or []

        node_index: dict[str, dict[str, Any]] = {n.get("id"): n for n in nodes_payload if isinstance(n, dict)}

        metric_requests, metric_by_request_id = cls._build_metric_requests(node_index)
        interface_requests, link_port_pairs, interface_node_links = cls._build_interface_requests(node_index, links_payload)

        errors: list[dict[str, str]] = []
        if metric_requests:
            try:
                metric_response = adapter.batch_metric_values(metric_requests)
            except Exception as exc:  # WeOps may time out on metric queries; do not fail the whole canvas.
                if _is_fatal_adapter_error(exc):
                    raise
                metric_response = {"items": cls._metric_error_items(metric_by_request_id, exc)}
                errors.append(
                    {
                        "scope": "metrics",
                        "code": "metric_query_failed",
                        "message": str(exc),
                    }
                )
        else:
            metric_response = {"items": []}

        if interface_requests:
            try:
                interface_response = adapter.batch_interface_status(interface_requests, include_summary=True)
            except Exception as exc:
                if _is_fatal_adapter_error(exc):
                    raise
                interface_response = {"items": [], "node_interface_summary": {}}
                errors.append(
                    {
                        "scope": "interfaces",
                        "code": "interface_query_failed",
                        "message": str(exc),
                    }
                )
        else:
            interface_response = {"items": [], "node_interface_summary": {}}

        runtime_metrics = cls._merge_runtime_metrics(metric_response, metric_by_request_id, topology)
        interface_items = list(interface_response.get("items") or [])

        link_runtime = cls._aggregate_links(link_port_pairs, interface_items, links_payload)
        node_runtime = cls._aggregate_nodes(node_index, runtime_metrics, interface_response, topology)

        return {
            "result": True,
            "data": {
                "nodes": node_runtime,
                "links": link_runtime,
                "errors": errors,
            },
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    def _build_metric_requests(cls, node_index: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        requests: list[dict[str, Any]] = []
        indexed: dict[str, dict[str, Any]] = {}
        for node in node_index.values():
            node_ref = _node_ref_from_view_set(node)
            for metric in node.get("metrics") or []:
                metric_order = metric.get("sort_order", 0)
                request_id = f"{node.get('id')}::{metric_order}::{metric.get('metric_field')}::{metric.get('result_table_id')}"
                requests.append(
                    {
                        "request_id": request_id,
                        "node_ref": node_ref,
                        "metric_ref": {
                            "metric_field": metric.get("metric_field"),
                            "result_table_id": metric.get("result_table_id"),
                        },
                        "dimensions": metric.get("dimensions") or {},
                        "condition_filter": metric.get("condition_filter") or [],
                        "display_mode": metric.get("display_mode")
                        or ("dimension" if metric.get("condition_filter") or metric.get("dimensions") else "aggregate"),
                        "aggregate_type": metric.get("aggregate_type") or "sum",
                    }
                )
                indexed[request_id] = {"node": node, "metric": metric}
        return requests, indexed

    @classmethod
    def _build_interface_requests(
        cls,
        node_index: dict[str, dict[str, Any]],
        links_payload: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, str]]:
        requests: list[dict[str, Any]] = []
        # link_id -> ordered list of port_pairs metadata for aggregation
        link_port_pairs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # request_id -> link_id for routing responses back to links
        interface_node_links: dict[str, str] = {}

        for link in links_payload:
            link_id = link.get("id") or ""
            if not link_id:
                continue
            if link.get("is_draft"):
                # Draft links don't yet reference real ports; skip them
                # from runtime queries but they may still be in canvas.
                continue
            for pair_index, pair in enumerate(link.get("port_pairs") or []):
                source_node = node_index.get(link.get("source_node_id") or "")
                target_node = node_index.get(link.get("target_node_id") or "")
                if source_node and (pair.get("source_interface") or {}).get("bk_inst_id"):
                    request_id = f"{link_id}::src::{pair_index}"
                    requests.append(
                        {
                            "request_id": request_id,
                            "node_ref": _node_ref_from_view_set(source_node),
                            "interface_ref": pair["source_interface"],
                        }
                    )
                    interface_node_links[request_id] = link_id
                    link_port_pairs[link_id].append({"endpoint": "source", "pair": pair, "request_id": request_id})

                if target_node and (pair.get("target_interface") or {}).get("bk_inst_id"):
                    request_id = f"{link_id}::dst::{pair_index}"
                    requests.append(
                        {
                            "request_id": request_id,
                            "node_ref": _node_ref_from_view_set(target_node),
                            "interface_ref": pair["target_interface"],
                        }
                    )
                    interface_node_links[request_id] = link_id
                    link_port_pairs[link_id].append({"endpoint": "target", "pair": pair, "request_id": request_id})

        return requests, link_port_pairs, interface_node_links

    @classmethod
    def _merge_runtime_metrics(
        cls,
        metric_response: dict[str, Any],
        metric_by_request_id: dict[str, dict[str, Any]],
        topology,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        for item in metric_response.get("items") or []:
            request_id = item.get("request_id") or ""
            meta = metric_by_request_id.get(request_id)
            if meta is None:
                # Item we didn't ask for, OR backend returned an unknown id
                # — don't lose the data, surface as best-effort.
                merged.append(
                    {
                        "request_id": request_id,
                        "metric_field": (item.get("metric_ref") or {}).get("metric_field"),
                        "result_table_id": (item.get("metric_ref") or {}).get("result_table_id"),
                        "sort_order": item.get("sort_order"),
                        "value": item.get("value"),
                        "status": item.get("status"),
                        "error_code": item.get("error_code"),
                        "error_message": item.get("error_message"),
                        "sample_time": item.get("sample_time"),
                        "stale": item.get("stale"),
                        "freshness_window": item.get("freshness_window"),
                        "unit": item.get("unit"),
                        "display_mode": item.get("display_mode"),
                        "aggregate_type": item.get("aggregate_type"),
                    }
                )
                continue
            node = meta["node"]
            metric = meta["metric"]
            merged.append(
                {
                    "request_id": request_id,
                    "node_id": node.get("id"),
                    "metric_field": metric.get("metric_field"),
                    "result_table_id": metric.get("result_table_id"),
                    "sort_order": metric.get("sort_order", 0),
                    "display_name": metric.get("display_name") or metric.get("metric_field"),
                    "unit": item.get("unit") or metric.get("unit") or "",
                    "value": item.get("value"),
                    "sample_time": item.get("sample_time"),
                    "stale": item.get("stale"),
                    "freshness_window": item.get("freshness_window"),
                    "status": item.get("status"),
                    "error_code": item.get("error_code"),
                    "error_message": item.get("error_message"),
                    "thresholds": metric.get("thresholds") or [],
                    "dimensions": metric.get("dimensions") or {},
                    "condition_filter": metric.get("condition_filter") or [],
                    "display_mode": metric.get("display_mode")
                    or ("dimension" if metric.get("condition_filter") or metric.get("dimensions") else "aggregate"),
                    "aggregate_type": metric.get("aggregate_type") or "sum",
                }
            )
        return merged

    @classmethod
    def _metric_error_items(
        cls,
        metric_by_request_id: dict[str, dict[str, Any]],
        error: Exception,
    ) -> list[dict[str, Any]]:
        message = str(error) or "WeOps 指标查询失败"
        return [
            {
                "request_id": request_id,
                "value": None,
                "unit": (meta.get("metric") or {}).get("unit") or "",
                "sample_time": None,
                "status": "error",
                "error_code": "metric_query_failed",
                "error_message": message,
            }
            for request_id, meta in metric_by_request_id.items()
        ]

    @classmethod
    def _aggregate_links(
        cls,
        link_port_pairs: dict[str, list[dict[str, Any]]],
        interface_items: list[dict[str, Any]],
        links_payload: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        interface_by_request_id = {item.get("request_id"): item for item in interface_items}
        link_titles = {link.get("id"): link for link in links_payload}

        results: list[dict[str, Any]] = []
        for link_id, pair_metas in link_port_pairs.items():
            selected_metrics = cls._normalize_interface_metric_fields(link_titles.get(link_id, {}).get("interface_metrics"))
            resolved_interfaces = []
            for pair_meta in pair_metas:
                request_id = pair_meta["request_id"]
                interface = interface_by_request_id.get(request_id)
                if interface is None:
                    continue
                resolved_interfaces.append(
                    {
                        "endpoint": pair_meta["endpoint"],
                        "oper_status": interface.get("oper_status"),
                        "admin_status": interface.get("admin_status"),
                        "status": interface.get("status"),
                        "error_code": interface.get("error_code"),
                        "stale": interface.get("stale"),
                        "freshness_window": interface.get("freshness_window"),
                        "metrics": cls._filter_interface_metrics(interface.get("metrics") or {}, selected_metrics),
                        "interface_name": (pair_meta["pair"].get(pair_meta["endpoint"] + "_interface") or {}).get("interface_name"),
                        "bk_inst_id": (pair_meta["pair"].get(pair_meta["endpoint"] + "_interface") or {}).get("bk_inst_id"),
                    }
                )

            status = resolve_link_status(resolved_interfaces)
            results.append(
                {
                    "id": link_id,
                    "source_node_id": link_titles.get(link_id, {}).get("source_node_id"),
                    "target_node_id": link_titles.get(link_id, {}).get("target_node_id"),
                    "status": status["status"],
                    "reason": status.get("reason"),
                    "interfaces": resolved_interfaces,
                    "interface_metrics": selected_metrics,
                    "is_draft": bool(link_titles.get(link_id, {}).get("is_draft")),
                }
            )

        return results

    @classmethod
    def _normalize_interface_metric_fields(cls, fields: Any) -> list[str]:
        if not isinstance(fields, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        for field in fields:
            if field in cls.INTERFACE_METRIC_FIELDS and field not in seen:
                seen.add(field)
                result.append(field)
        return result

    @classmethod
    def _filter_interface_metrics(
        cls,
        metrics: dict[str, Any],
        selected_fields: list[str],
    ) -> dict[str, Any]:
        if not selected_fields:
            return dict(metrics)
        return {field: metrics[field] for field in selected_fields if field in metrics}

    @classmethod
    def _aggregate_nodes(
        cls,
        node_index: dict[str, dict[str, Any]],
        runtime_metrics: list[dict[str, Any]],
        interface_response: dict[str, Any],
        topology,
    ) -> list[dict[str, Any]]:
        node_interface_summary = interface_response.get("node_interface_summary") or {}

        # Group runtime metrics by the request owner. Matching only by
        # metric_field/result_table_id is ambiguous because different nodes
        # often bind the same WeOps metric.
        metrics_by_node_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for metric in runtime_metrics:
            node_id = metric.get("node_id")
            if node_id:
                metrics_by_node_id[str(node_id)].append(metric)

        results: list[dict[str, Any]] = []
        for node in node_index.values():
            node_metrics = metrics_by_node_id.get(str(node.get("id")), [])
            configured_metrics = node.get("metrics") or []
            outer_color = resolve_node_outer_color(configured_metrics, node_metrics)
            key = f"{node.get('bk_obj_id')}:{node.get('bk_inst_id')}"
            summary = node_interface_summary.get(key)

            results.append(
                {
                    "id": node.get("id"),
                    "bk_obj_id": node.get("bk_obj_id"),
                    "bk_inst_id": node.get("bk_inst_id"),
                    "bk_inst_name": node.get("bk_inst_name"),
                    "outer_color": outer_color,
                    "outer_color_unknown": outer_color is None,
                    "metrics": node_metrics,
                    "interface_summary": summary,
                    "errors": cls._errors_for_node(node, node_metrics),
                }
            )

        return results

    @staticmethod
    def _errors_for_node(node: dict[str, Any], runtime_metrics: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Surface validation-time errors that don't kill the whole node."""
        errors: list[dict[str, str]] = []
        for metric in runtime_metrics:
            if metric.get("status") != "ok" and metric.get("error_code"):
                errors.append(
                    {
                        "code": metric.get("error_code") or "unknown",
                        "message": metric.get("error_message") or "未知错误",
                        "scope": "metric",
                        "metric_field": metric.get("metric_field") or "",
                    }
                )
        return errors


def _node_ref_from_view_set(node: dict[str, Any]) -> dict[str, Any]:
    """Reduce a node view_set entry to the WeOps ``node_ref`` shape."""
    return {
        "bk_obj_id": node.get("bk_obj_id"),
        "bk_inst_id": node.get("bk_inst_id"),
        "network_collect_task_id": node.get("network_collect_task_id") or 0,
        "network_collect_instance_id": node.get("network_collect_instance_id") or 0,
        "plugin_group_id": node.get("plugin_group_id") or 0,
        "plugin_template_id": node.get("plugin_template_id") or 0,
    }


def _is_fatal_adapter_error(error: Exception) -> bool:
    return getattr(error, "code", "") == "weops_token_invalid" or getattr(error, "status_code", None) in (401, 403)
