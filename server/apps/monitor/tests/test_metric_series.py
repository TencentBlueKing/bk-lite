from types import SimpleNamespace

import pytest

from apps.monitor.services.metric_series import (
    build_monitor_instance_rows,
    canonical_dimension_names,
    conversation_display_name,
    endpoint_display_name,
    fold_instant_rows,
    fold_range_series,
    format_protocol_short_name,
    instance_matches_protocol,
    unwrap_limiting_query,
    validate_collect_type,
    validate_instance_id_count,
    validate_limit,
    validate_metric_name,
    validate_mode,
    window_selector,
)


def test_validate_mode_and_collect_type():
    assert validate_mode("range") == "range"
    assert validate_mode("INSTANT") == "instant"
    with pytest.raises(ValueError):
        validate_mode("batch")
    assert validate_collect_type(None) is None
    assert validate_collect_type("sFlow") == "sflow"
    with pytest.raises(ValueError):
        validate_collect_type("ipfix")


def test_validate_limit_bounds():
    assert validate_limit(None) == 10
    assert validate_limit(3) == 3
    with pytest.raises(ValueError):
        validate_limit(0)
    with pytest.raises(ValueError):
        validate_limit(101)
    assert validate_metric_name("device_flow_bytes_rate") == "device_flow_bytes_rate"
    with pytest.raises(ValueError):
        validate_metric_name("  ")
    validate_instance_id_count(["a"] * 200)
    with pytest.raises(ValueError):
        validate_instance_id_count(["a"] * 201)


def test_canonical_dimension_names_merge_flow_aliases():
    assert canonical_dimension_names(
        [
            {"name": "src_ip"},
            {"name": "dst_ip"},
            {"name": "header_protocol"},
            {"name": "src"},
            {"name": "instance_id"},
        ]
    ) == ["src", "dst", "protocol"]


def test_unwrap_topk_keeps_inner_expr():
    query = "topk(10, sum(netflow_in_bytes) by (instance_id, src))"
    assert unwrap_limiting_query(query) == "sum(netflow_in_bytes) by (instance_id, src)"
    assert unwrap_limiting_query("sum(x) by (src)") == "sum(x) by (src)"


def test_window_selector_uses_whole_seconds():
    assert window_selector(100.0, 3700.4) == "3600s"
    assert window_selector(10.0, 10.5) == "1s"


def test_protocol_short_name_maps_iana():
    assert format_protocol_short_name("6") == "TCP"
    assert format_protocol_short_name("17") == "UDP"
    assert format_protocol_short_name("tcp") == "TCP"
    assert format_protocol_short_name("99") == "Proto-99"


def test_conversation_display_name():
    assert conversation_display_name({"src": "10.1.1.23", "dst": "172.16.8.20", "dst_port": "443"}) == "10.1.1.23 → 172.16.8.20:443"
    assert conversation_display_name({"src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "dst_port": "0"}) == "10.0.0.1 → 10.0.0.2"


def test_endpoint_display_name():
    assert endpoint_display_name({"src": "10.1.1.23", "src_port": "54321"}, ip_keys=("src", "src_ip"), port_key="src_port") == "10.1.1.23:54321"
    assert endpoint_display_name({"dst_ip": "172.16.8.20", "dst_port": "443"}, ip_keys=("dst", "dst_ip"), port_key="dst_port") == "172.16.8.20:443"
    assert endpoint_display_name({"src": "10.0.0.1", "src_port": "0"}, ip_keys=("src", "src_ip"), port_key="src_port") == "10.0.0.1"


def test_instance_rows_filter_protocol_and_sort():
    rows = build_monitor_instance_rows(
        [
            SimpleNamespace(
                id="sw-2",
                name="core-b",
                ip="10.0.0.2",
                enabled_protocols=["sflow"],
                monitor_object=SimpleNamespace(name="Switch"),
            ),
            SimpleNamespace(
                id="sw-1",
                name="core-a",
                ip="10.0.0.1",
                enabled_protocols=["netflow"],
                monitor_object=SimpleNamespace(name="Switch"),
            ),
            SimpleNamespace(
                id="host-1",
                name="web",
                ip="10.0.0.9",
                enabled_protocols=[],
                monitor_object=SimpleNamespace(name="Host"),
            ),
        ],
        protocol="netflow",
    )
    assert rows == [
        {
            "instance_id": "sw-1",
            "display_name": "core-a (10.0.0.1)",
            "ip": "10.0.0.1",
            "object_name": "Switch",
            "enabled_protocols": ["netflow"],
        }
    ]
    assert instance_matches_protocol(SimpleNamespace(enabled_protocols=["netflow", "sflow"]), None) is True


def test_fold_instant_sums_instances_and_maps_protocol():
    rows = fold_instant_rows(
        [
            {"metric": {"instance_id": "a", "protocol": "6"}, "value": [1, "10"]},
            {"metric": {"instance_id": "b", "protocol": "6"}, "value": [1, "5"]},
            {"metric": {"instance_id": "a", "protocol": "17"}, "value": [1, "2"]},
        ],
        dimensions=["protocol"],
        limit=10,
    )
    assert rows[0]["name"] == "TCP"
    assert rows[0]["value"] == 15.0
    assert rows[0]["protocol"] == "TCP"
    assert rows[1]["name"] == "UDP"
    assert rows[1]["value"] == 2.0


def test_fold_instant_overview_is_single_total():
    rows = fold_instant_rows(
        [
            {"metric": {"instance_id": "a"}, "value": [1, "10"]},
            {"metric": {"instance_id": "b"}, "value": [1, "4"]},
        ],
        dimensions=[],
        limit=10,
    )
    assert rows == [{"rank": 1, "name": "total", "value": 14.0}]


def test_fold_instant_conversation_builds_name():
    rows = fold_instant_rows(
        [
            {
                "metric": {
                    "instance_id": "a",
                    "src": "10.1.1.23",
                    "dst": "172.16.8.20",
                    "protocol": "6",
                    "dst_port": "443",
                },
                "value": [1, "80"],
            }
        ],
        dimensions=["src", "dst", "protocol", "dst_port"],
        limit=10,
    )
    assert rows[0]["name"] == "10.1.1.23 → 172.16.8.20:443"
    assert rows[0]["src"] == "10.1.1.23"
    assert rows[0]["dst"] == "172.16.8.20"
    assert rows[0]["protocol"] == "TCP"


def test_fold_instant_endpoint_builds_ip_port_name():
    src_rows = fold_instant_rows(
        [
            {
                "metric": {"instance_id": "a", "src": "10.1.1.23", "src_port": "54321"},
                "value": [1, "30"],
            },
            {
                "metric": {"instance_id": "b", "src_ip": "10.1.1.23", "src_port": "54321"},
                "value": [1, "10"],
            },
        ],
        dimensions=["src", "src_port"],
        limit=10,
    )
    assert src_rows[0]["name"] == "10.1.1.23:54321"
    assert src_rows[0]["value"] == 40.0

    dst_rows = fold_instant_rows(
        [
            {
                "metric": {"instance_id": "a", "dst_ip": "172.16.8.20", "dst_port": "443"},
                "value": [1, "80"],
            }
        ],
        dimensions=["dst", "dst_port"],
        limit=10,
    )
    assert dst_rows[0]["name"] == "172.16.8.20:443"
    assert dst_rows[0]["dst"] == "172.16.8.20"
    assert dst_rows[0]["dst_port"] == "443"


def test_fold_range_merges_timestamps():
    series = fold_range_series(
        [
            {"metric": {"instance_id": "a", "protocol": "6"}, "values": [[1, "10"], [2, "20"]]},
            {"metric": {"instance_id": "b", "protocol": "6"}, "values": [[1, "5"], [3, "1"]]},
        ],
        dimensions=["protocol"],
    )
    assert series["TCP"] == [[1.0, 15.0], [2.0, 20.0], [3.0, 1.0]]
