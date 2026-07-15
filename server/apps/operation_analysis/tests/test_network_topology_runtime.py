# -*- coding: utf-8 -*-
"""
Tests for the runtime aggregation layer.

Covers ``resolve_node_outer_color`` and ``resolve_link_status`` — the two
pure functions that drive the canvas' status display — plus the runtime
service's cache management and end-to-end ``build_runtime`` orchestration.

Real ``NetworkTopology`` rows are used (with the view_sets JSON we
persist) — no separate connection tables exist post-refactor.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.operation_analysis.models.models import NODE_OUTER_COLOR_UNKNOWN, Directory, NetworkTopology
from apps.operation_analysis.services.network_topology.runtime import NetworkTopologyRuntimeService, resolve_link_status, resolve_node_outer_color
from apps.operation_analysis.services.network_topology.weops_adapter import WeOpsTopologyAdapterError

# --------------------------------------------------------------------------- #
# resolve_node_outer_color                                                      #
# --------------------------------------------------------------------------- #


def _metric(field, result_table_id, thresholds, **extras):
    payload = {
        "metric_field": field,
        "result_table_id": result_table_id,
        "display_name": extras.pop("display_name", field),
        "thresholds": thresholds,
        "dimensions": {},
    }
    payload.update(extras)
    return payload


def _runtime(field, result_table_id, value, status="ok", **extras):
    payload = {
        "metric_field": field,
        "result_table_id": result_table_id,
        "value": value,
        "status": status,
        "unit": "",
        "sample_time": None,
    }
    payload.update(extras)
    return payload


def test_resolve_node_outer_color_single_metric_deepest_hit_wins():
    metrics = [
        _metric(
            "ifHCInOctets",
            "snmp_network",
            [{"value": 0, "color": "#22c55e"}, {"value": 100, "color": "#dc2626"}],
        )
    ]
    runtime_metrics = [_runtime("ifHCInOctets", "snmp_network", 150.0)]

    assert resolve_node_outer_color(metrics, runtime_metrics) == "#dc2626"


def test_resolve_node_outer_color_picks_deepest_metric_across_multiple():
    metrics = [
        _metric(
            "ifInErrors",
            "snmp_network",
            [{"value": 0, "color": "#22c55e"}, {"value": 80, "color": "#eab308"}],
        ),
        _metric(
            "ifHCInOctets",
            "snmp_network",
            [
                {"value": 0, "color": "#22c55e"},
                {"value": 80, "color": "#eab308"},
                {"value": 100, "color": "#dc2626"},
            ],
        ),
    ]
    runtime_metrics = [
        _runtime("ifInErrors", "snmp_network", 90.0),  # hits level 1 (yellow)
        _runtime("ifHCInOctets", "snmp_network", 130.0),  # hits level 2 (red, deepest)
    ]

    assert resolve_node_outer_color(metrics, runtime_metrics) == "#dc2626"


def test_resolve_node_outer_color_breaks_ties_by_metric_order():
    metrics = [
        _metric("first", "t", [{"value": 0, "color": "#aaa"}, {"value": 50, "color": "#bbb"}]),
        _metric("second", "t", [{"value": 0, "color": "#ccc"}, {"value": 50, "color": "#ddd"}]),
    ]
    runtime_metrics = [
        _runtime("first", "t", 100.0),  # hits level 1 → #bbb
        _runtime("second", "t", 100.0),  # hits level 1 → #ddd
    ]

    # Both at level 1, first metric wins.
    assert resolve_node_outer_color(metrics, runtime_metrics) == "#bbb"


def test_resolve_node_outer_color_baseline_uses_smallest_threshold():
    metrics = [
        _metric(
            "cpu",
            "t",
            [{"value": 10, "color": "#low"}, {"value": 80, "color": "#high"}],
        )
    ]
    runtime_metrics = [_runtime("cpu", "t", 5.0)]  # below smallest threshold

    # Spec: "Metric value below all thresholds uses baseline color".
    assert resolve_node_outer_color(metrics, runtime_metrics) == "#low"


def test_resolve_node_outer_color_descending_thresholds_use_numeric_baseline():
    metrics = [
        _metric(
            "packet_loss",
            "snmp_network",
            [
                {"value": 70, "color": "#dc2626"},
                {"value": 30, "color": "#d97706"},
                {"value": 0, "color": "#2563eb"},
            ],
        )
    ]
    runtime_metrics = [_runtime("packet_loss", "snmp_network", 6.0)]

    assert resolve_node_outer_color(metrics, runtime_metrics) == "#2563eb"


def test_resolve_node_outer_color_metric_with_no_data_excluded_from_aggregation():
    metrics = [
        _metric("a", "t", [{"value": 0, "color": "#x"}]),
        _metric("b", "t", [{"value": 0, "color": "#y"}, {"value": 80, "color": "#z"}]),
    ]
    runtime_metrics = [
        _runtime("a", "t", None, status="error", error_code="metric_no_data"),
        _runtime("b", "t", 90.0),
    ]

    assert resolve_node_outer_color(metrics, runtime_metrics) == "#z"


def test_resolve_node_outer_color_all_metrics_no_data_returns_none():
    metrics = [
        _metric("a", "t", [{"value": 0, "color": "#x"}]),
        _metric("b", "t", [{"value": 0, "color": "#y"}]),
    ]
    runtime_metrics = [
        _runtime("a", "t", None, status="error"),
        _runtime("b", "t", None, status="error"),
    ]

    # None → caller maps to NODE_OUTER_COLOR_UNKNOWN.
    assert resolve_node_outer_color(metrics, runtime_metrics) is None


def test_resolve_node_outer_color_with_no_metrics_configured_returns_none():
    assert resolve_node_outer_color([], []) is None


def test_resolve_node_outer_color_distinguishes_same_field_across_result_tables():
    metrics = [
        _metric("cpu", "table_a", [{"value": 0, "color": "#aaa"}, {"value": 50, "color": "#a2"}]),
        _metric("cpu", "table_b", [{"value": 0, "color": "#bbb"}, {"value": 80, "color": "#b2"}]),
    ]
    runtime_metrics = [
        _runtime("cpu", "table_a", 10.0),  # baseline → #aaa
        _runtime("cpu", "table_b", 90.0),  # hits level 1 → #b2
    ]

    # Different result_table_id → independent hit selection; the deep one wins.
    assert resolve_node_outer_color(metrics, runtime_metrics) == "#b2"


def test_resolve_node_outer_color_nan_and_string_values_excluded():
    metrics = [
        _metric("cpu", "t", [{"value": 0, "color": "#real"}]),
    ]

    assert resolve_node_outer_color(metrics, [_runtime("cpu", "t", float("nan"))]) is None
    assert resolve_node_outer_color(metrics, [_runtime("cpu", "t", "not-a-number")]) is None


# --------------------------------------------------------------------------- #
# resolve_link_status                                                           #
# --------------------------------------------------------------------------- #


def test_resolve_link_status_all_up_returns_normal():
    items = [
        {"oper_status": "up", "status": "ok"},
        {"oper_status": "up", "status": "ok"},
    ]
    assert resolve_link_status(items)["status"] == "normal"


def test_resolve_link_status_any_down_returns_critical():
    items = [
        {"oper_status": "up", "status": "ok"},
        {"oper_status": "down", "status": "ok"},
        {"oper_status": "up", "status": "ok"},
    ]
    assert resolve_link_status(items) == {"status": "critical", "reason": "interface_down"}


def test_resolve_link_status_no_interface_returns_unknown():
    assert resolve_link_status([]) == {"status": "unknown", "reason": "no_interface"}


def test_resolve_link_status_missing_data_returns_unknown_not_down():
    items = [
        {"oper_status": "up", "status": "ok"},
        {"oper_status": "unknown", "status": "error", "error_code": "status_no_data"},
    ]
    # Spec: "Missing interface status turns link unknown" — must NOT turn into
    # ``down`` just because the data is missing.
    assert resolve_link_status(items) == {"status": "unknown", "reason": "interface_unknown"}


def test_resolve_link_status_testing_is_unknown():
    items = [{"oper_status": "testing", "status": "ok"}]
    # ``testing`` is not ``down`` so we fall through to unknown per the
    # explicit ``up/down`` rule (design.md §9.1).
    assert resolve_link_status(items)["status"] == "unknown"


def test_resolve_link_status_interface_with_status_error_returns_unknown():
    items = [
        {"oper_status": "up", "status": "ok"},
        {"oper_status": "up", "status": "error", "error_code": "metric_query_failed"},
    ]
    assert resolve_link_status(items)["status"] == "unknown"


# --------------------------------------------------------------------------- #
# cache + TTL                                                                   #
# --------------------------------------------------------------------------- #


def _build_topology():
    directory = Directory.objects.create(name="网络拓扑目录", groups=[1])
    return NetworkTopology.objects.create(
        name="核心网拓扑",
        directory=directory,
        groups=[1],
        base_url="https://weops.example.com",
        token="t",
        view_sets={"nodes": [], "links": []},
    )


@pytest.mark.django_db
def test_cache_payload_includes_generated_at_iso_string():
    payload = NetworkTopologyRuntimeService.cache_payload({"nodes": [{"id": "n1"}]})
    assert payload["nodes"] == [{"id": "n1"}]
    assert "_generated_at" in payload
    # Cheap sanity check: ISO 8601 round-trip.
    assert "T" in payload["_generated_at"]


@pytest.mark.django_db
def test_fresh_cached_payload_returns_cache_within_ttl_and_strips_metadata():
    topology = _build_topology()
    payload = NetworkTopologyRuntimeService.cache_payload({"nodes": [{"id": "n1"}]})
    topology.last_runtime_cache = payload
    topology.save()

    result = NetworkTopologyRuntimeService.fresh_cached_payload(topology)
    assert result == {"nodes": [{"id": "n1"}]}
    assert "_generated_at" not in result


@pytest.mark.django_db
def test_fresh_cached_payload_returns_empty_when_expired():
    topology = _build_topology()
    topology.last_runtime_cache = NetworkTopologyRuntimeService.cache_payload({"nodes": [{"id": "n1"}]})
    topology.save()
    # Force expiry by rewriting the cached timestamp.
    expired = timezone.now() - timedelta(seconds=NetworkTopologyRuntimeService.CACHE_TTL_SECONDS + 30)
    topology.last_runtime_cache["_generated_at"] = expired.isoformat()
    topology.save()

    result = NetworkTopologyRuntimeService.fresh_cached_payload(topology)
    assert result == {}


@pytest.mark.django_db
def test_fresh_cached_payload_returns_empty_when_missing_metadata():
    topology = _build_topology()
    topology.last_runtime_cache = {"nodes": [{"id": "n1"}]}
    topology.save()
    assert NetworkTopologyRuntimeService.fresh_cached_payload(topology) == {}


# --------------------------------------------------------------------------- #
# build_runtime (orchestration)                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_build_runtime_aggregates_node_color_and_link_status_from_view_sets():
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-1",
                "bk_obj_id": "bk_switch",
                "bk_inst_id": 10001,
                "bk_inst_name": "core-switch-01",
                "ip_addr": "10.0.0.1",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_group_id": 3,
                "plugin_template_id": "cisco_c9300",
                "position": {"x": 100, "y": 100},
                "style": {},
                "metrics": [
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "display_name": "入口流量",
                        "unit": "bps",
                        "dimensions": {},
                        "thresholds": [
                            {"value": 0, "color": "#22c55e"},
                            {"value": 100, "color": "#dc2626"},
                        ],
                    }
                ],
            }
        ],
        "links": [
            {
                "id": "link-1",
                "source_node_id": "node-1",
                "target_node_id": "node-1",
                "is_draft": False,
                "interface_metrics": ["ifInOctets_5min"],
                "port_pairs": [
                    {
                        "source_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90001, "interface_name": "GigE0/1"},
                        "target_interface": {"bk_obj_id": "bk_interface", "bk_inst_id": 90002, "interface_name": "GigE0/2"},
                    }
                ],
                "style": {},
            }
        ],
    }
    topology.save()

    class FakeAdapter:
        def batch_metric_values(self, items):
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "node_ref": items[0]["node_ref"],
                        "metric_ref": items[0]["metric_ref"],
                        "value": 150.0,
                        "unit": "bps",
                        "sample_time": "2026-07-10T10:00:00+08:00",
                        "status": "ok",
                    }
                ]
            }

        def batch_interface_status(self, items, include_summary=True):
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "oper_status": "up",
                        "admin_status": "up",
                        "status": "ok",
                        "metrics": {
                            "ifInOctets_5min": {"value": 12.5, "unit": "bps"},
                            "ifOutOctets_5min": {"value": 33.5, "unit": "bps"},
                        },
                    },
                    {
                        "request_id": items[1]["request_id"],
                        "oper_status": "down",
                        "admin_status": "up",
                        "status": "ok",
                        "metrics": {
                            "ifInOctets_5min": {"value": 21.5, "unit": "bps"},
                            "ifOutOctets_5min": {"value": 44.5, "unit": "bps"},
                        },
                    },
                ],
                "node_interface_summary": {"bk_switch:10001": {"total": 1, "up": 0, "down": 1, "unknown": 0}},
            }

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())

    nodes = response["data"]["nodes"]
    links = response["data"]["links"]
    assert nodes[0]["outer_color"] == "#dc2626"
    assert nodes[0]["outer_color_unknown"] is False
    assert nodes[0]["interface_summary"]["down"] == 1

    # link-1 has one up + one down → critical
    link = next(link for link in links if link["id"] == "link-1")
    assert link["status"] == "critical"
    assert link["interface_metrics"] == ["ifInOctets_5min"]
    assert link["interfaces"][0]["metrics"] == {"ifInOctets_5min": {"value": 12.5, "unit": "bps"}}
    assert "ifOutOctets_5min" not in link["interfaces"][0]["metrics"]


@pytest.mark.django_db
def test_build_runtime_unknown_color_when_metrics_lack_data():
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-1",
                "bk_obj_id": "bk_switch",
                "bk_inst_id": 10001,
                "bk_inst_name": "core-switch-01",
                "ip_addr": "10.0.0.1",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_group_id": 3,
                "plugin_template_id": "cisco_c9300",
                "position": {"x": 0, "y": 0},
                "style": {},
                "metrics": [
                    {
                        "metric_field": "ifHCInOctets",
                        "result_table_id": "snmp_network",
                        "display_name": "入口流量",
                        "unit": "bps",
                        "dimensions": {},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ],
            }
        ],
        "links": [],
    }
    topology.save()

    class FakeAdapter:
        def batch_metric_values(self, items):
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "node_ref": items[0]["node_ref"],
                        "metric_ref": items[0]["metric_ref"],
                        "value": None,
                        "unit": "bps",
                        "sample_time": None,
                        "status": "error",
                        "error_code": "metric_no_data",
                    }
                ]
            }

        def batch_interface_status(self, items, include_summary=True):
            return {"items": [], "node_interface_summary": {}}

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())
    node = response["data"]["nodes"][0]
    assert node["outer_color"] is None
    assert node["outer_color_unknown"] is True
    assert any(err["code"] == "metric_no_data" for err in node["errors"])


@pytest.mark.django_db
def test_build_runtime_routes_same_metric_to_owning_node_by_request_id():
    """Same metric/table may be bound on multiple nodes; runtime must not
    fan one response out to every matching metric definition."""
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-a",
                "bk_obj_id": "bk_switch",
                "bk_inst_id": 10001,
                "bk_inst_name": "switch-a",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_template_id": "tpl",
                "position": {"x": 0, "y": 0},
                "metrics": [
                    {
                        "metric_field": "ifInUcastPkts",
                        "result_table_id": "snmp_network",
                        "display_name": "入口单播包",
                        "unit": "pps",
                        "dimensions": {"ifDescr": "eth0"},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ],
            },
            {
                "id": "node-b",
                "bk_obj_id": "bk_router",
                "bk_inst_id": 10002,
                "bk_inst_name": "router-b",
                "network_collect_task_id": 13,
                "network_collect_instance_id": 346,
                "plugin_template_id": "tpl",
                "position": {"x": 100, "y": 0},
                "metrics": [
                    {
                        "metric_field": "ifInUcastPkts",
                        "result_table_id": "snmp_network",
                        "display_name": "入口单播包",
                        "unit": "pps",
                        "dimensions": {"ifDescr": "eth1"},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ],
            },
        ],
        "links": [],
    }
    topology.save()

    class FakeAdapter:
        def batch_metric_values(self, items):
            node_b_request = next(item for item in items if item["request_id"].startswith("node-b::"))
            return {
                "items": [
                    {
                        "request_id": node_b_request["request_id"],
                        "node_ref": node_b_request["node_ref"],
                        "metric_ref": node_b_request["metric_ref"],
                        "value": 77,
                        "unit": "pps",
                        "status": "ok",
                        "sample_time": "2026-07-10T10:00:00+08:00",
                        "stale": True,
                        "freshness_window": "7d",
                    }
                ]
            }

        def batch_interface_status(self, items, include_summary=True):
            return {"items": [], "node_interface_summary": {}}

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())

    by_id = {node["id"]: node for node in response["data"]["nodes"]}
    assert by_id["node-a"]["metrics"] == []
    assert by_id["node-b"]["metrics"][0]["request_id"].startswith("node-b::")
    assert by_id["node-b"]["metrics"][0]["node_id"] == "node-b"
    assert by_id["node-b"]["metrics"][0]["value"] == 77
    assert by_id["node-b"]["metrics"][0]["stale"] is True
    assert by_id["node-b"]["metrics"][0]["freshness_window"] == "7d"


@pytest.mark.django_db
def test_build_runtime_passes_metric_display_mode_and_aggregate_type():
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-a",
                "bk_obj_id": "bk_switch",
                "bk_inst_id": 10001,
                "bk_inst_name": "switch-a",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_template_id": "tpl",
                "position": {"x": 0, "y": 0},
                "metrics": [
                    {
                        "metric_field": "ifInOctets_5min",
                        "result_table_id": "snmp_network",
                        "display_name": "入网总流速",
                        "unit": "bps",
                        "display_mode": "aggregate",
                        "aggregate_type": "sum",
                        "dimensions": {"ifDescr": "eth0"},
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ],
            }
        ],
        "links": [],
    }
    topology.save()
    captured_items = []

    class FakeAdapter:
        def batch_metric_values(self, items):
            captured_items.extend(items)
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "metric_ref": items[0]["metric_ref"],
                        "value": 88,
                        "unit": "bps",
                        "status": "ok",
                    }
                ]
            }

        def batch_interface_status(self, items, include_summary=True):
            return {"items": [], "node_interface_summary": {}}

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())

    assert captured_items[0]["display_mode"] == "aggregate"
    assert captured_items[0]["aggregate_type"] == "sum"
    assert response["data"]["nodes"][0]["metrics"][0]["display_mode"] == "aggregate"
    assert response["data"]["nodes"][0]["metrics"][0]["aggregate_type"] == "sum"


@pytest.mark.django_db
def test_build_runtime_keeps_duplicate_node_metrics_separate_by_sort_order():
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-a",
                "bk_obj_id": "bk_firewall",
                "bk_inst_id": 10001,
                "bk_inst_name": "firewall-a",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_template_id": "tpl",
                "position": {"x": 0, "y": 0},
                "metrics": [
                    {
                        "metric_field": "ifInDiscards",
                        "result_table_id": "snmp_network",
                        "display_name": "入口丢包",
                        "unit": "count",
                        "display_mode": "aggregate",
                        "aggregate_type": "max",
                        "sort_order": 0,
                        "thresholds": [{"value": 5, "color": "#d97706"}],
                    },
                    {
                        "metric_field": "ifInDiscards",
                        "result_table_id": "snmp_network",
                        "display_name": "入口丢包",
                        "unit": "count",
                        "display_mode": "aggregate",
                        "aggregate_type": "sum",
                        "sort_order": 1,
                        "thresholds": [{"value": 50, "color": "#dc2626"}],
                    },
                ],
            }
        ],
        "links": [],
    }
    topology.save()
    captured_items = []

    class FakeAdapter:
        def batch_metric_values(self, items):
            captured_items.extend(items)
            return {
                "items": [
                    {
                        "request_id": items[0]["request_id"],
                        "metric_ref": items[0]["metric_ref"],
                        "value": 6,
                        "unit": "count",
                        "status": "ok",
                    },
                    {
                        "request_id": items[1]["request_id"],
                        "metric_ref": items[1]["metric_ref"],
                        "value": 0,
                        "unit": "count",
                        "status": "ok",
                    },
                ]
            }

        def batch_interface_status(self, items, include_summary=True):
            return {"items": [], "node_interface_summary": {}}

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())

    assert len({item["request_id"] for item in captured_items}) == 2
    assert "::0::ifInDiscards::" in captured_items[0]["request_id"]
    assert "::1::ifInDiscards::" in captured_items[1]["request_id"]
    metrics = response["data"]["nodes"][0]["metrics"]
    assert [metric["sort_order"] for metric in metrics] == [0, 1]
    assert [metric["value"] for metric in metrics] == [6, 0]
    assert metrics[0]["request_id"] != metrics[1]["request_id"]


@pytest.mark.django_db
def test_build_runtime_unknown_color_falls_back_to_unknown_gray_constant():
    """The frontend maps ``outer_color == None + outer_color_unknown ==
    True`` to ``NODE_OUTER_COLOR_UNKNOWN`` (#64748b). We expose the constant
    here so the contract is explicit and avoids frontend magic numbers."""
    assert NODE_OUTER_COLOR_UNKNOWN == "#64748b"


@pytest.mark.django_db
def test_build_runtime_degrades_metric_batch_failure_without_losing_canvas_runtime():
    topology = _build_topology()
    topology.view_sets = {
        "nodes": [
            {
                "id": "node-a",
                "bk_obj_id": "bk_firewall",
                "bk_inst_id": 10001,
                "bk_inst_name": "firewall-a",
                "network_collect_task_id": 12,
                "network_collect_instance_id": 345,
                "plugin_template_id": "tpl",
                "position": {"x": 0, "y": 0},
                "metrics": [
                    {
                        "metric_field": "ifInUcastPkts",
                        "result_table_id": "snmp_network",
                        "display_name": "入口单播包",
                        "unit": "pps",
                        "sort_order": 0,
                        "thresholds": [{"value": 0, "color": "#22c55e"}],
                    }
                ],
            }
        ],
        "links": [],
    }
    topology.save()

    class FakeAdapter:
        def batch_metric_values(self, items):
            raise WeOpsTopologyAdapterError(
                "WeOps 请求失败: Read timed out",
                code="weops_unavailable",
                status_code=502,
            )

        def batch_interface_status(self, items, include_summary=True):
            return {"items": [], "node_interface_summary": {}}

    response = NetworkTopologyRuntimeService.build_runtime(topology, FakeAdapter())

    assert response["result"] is True
    assert response["data"]["errors"][0]["scope"] == "metrics"
    node = response["data"]["nodes"][0]
    assert node["outer_color"] is None
    assert node["id"] == "node-a"
    assert node["metrics"][0]["status"] == "error"
    assert node["metrics"][0]["error_code"] == "metric_query_failed"
    assert node["metrics"][0]["value"] is None
