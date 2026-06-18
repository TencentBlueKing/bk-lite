import json
from pathlib import Path

import yaml


FLOW_METRICS_ROOT = Path(__file__).resolve().parents[1] / "support-files" / "plugins" / "Telegraf"
MONITOR_ROOT = Path(__file__).resolve().parents[1]
LANGUAGE_ROOT = MONITOR_ROOT / "language"

FLOW_PROTOCOLS = ("netflow", "sflow")
FLOW_OBJECTS = ("switch", "router", "firewall", "loadbalance")
FLOW_MONITOR_OBJECTS = ("Switch", "Router", "Firewall", "Loadbalance")
FLOW_CORE_METRICS = [
    "device_flow_bytes_rate",
    "device_flow_packets_rate",
    "device_flow_in_bytes_rate",
    "device_flow_out_bytes_rate",
    "device_flow_in_packets_rate",
    "device_flow_out_packets_rate",
    "device_flow_avg_packet_size",
    "device_flow_effective_sampling_rate",
]
FLOW_ADVANCED_METRICS = [
    "device_flow_interface_bytes_rate",
    "device_flow_interface_packets_rate",
    "device_flow_top_interfaces_by_bytes",
    "device_flow_protocol_bytes_rate",
    "device_flow_protocol_packets_rate",
    "device_flow_dst_port_bytes_rate",
    "device_flow_dst_port_packets_rate",
    "device_flow_src_port_bytes_rate",
    "device_flow_top_src_bytes_rate",
    "device_flow_top_dst_bytes_rate",
    "device_flow_top_src_packets_rate",
    "device_flow_top_dst_packets_rate",
    "device_flow_top_conversation_bytes_rate",
]
FLOW_METRICS = FLOW_CORE_METRICS + FLOW_ADVANCED_METRICS
FLOW_GROUPS = {
    "Traffic Overview",
    "Sampling",
    "Interface Traffic",
    "Protocol",
    "Application Port",
    "Endpoint",
    "Conversation",
}
OLD_FLOW_METRICS = {
    "device_total_incoming_netflow_traffic",
    "device_total_outgoing_netflow_traffic",
    "device_total_incoming_sflow_traffic",
    "device_total_outgoing_sflow_traffic",
}
HIGH_CARDINALITY_METRICS = {
    "device_flow_top_src_bytes_rate",
    "device_flow_top_dst_bytes_rate",
    "device_flow_top_src_packets_rate",
    "device_flow_top_dst_packets_rate",
    "device_flow_top_conversation_bytes_rate",
}


def _flow_metric_files():
    return sorted(
        path
        for protocol in FLOW_PROTOCOLS
        for path in (FLOW_METRICS_ROOT / protocol).glob("*/metrics.json")
    )


def test_flow_traffic_metric_queries_use_effective_sampling_rate():
    flow_metric_files = _flow_metric_files()

    assert flow_metric_files

    missing_sampling_rate_queries = []
    for path in flow_metric_files:
        payload = json.loads(path.read_text())
        for metric in payload.get("metrics", []):
            query = metric.get("query", "")
            if ("_bytes" in metric["name"] or "_packets" in metric["name"]) and "effective_sampling_rate" not in query:
                missing_sampling_rate_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

    assert missing_sampling_rate_queries == []


def test_flow_traffic_queries_use_telegraf_metric_names():
    expected_metric_names = {
        "netflow": ("netflow_in_bytes", "netflow_out_bytes"),
        "sflow": ("sflow_bytes",),
    }
    metric_files = _flow_metric_files()

    assert metric_files

    unsupported_queries = []
    for path in metric_files:
        protocol = path.parts[-3]
        payload = json.loads(path.read_text())
        for metric in payload.get("metrics", []):
            if not metric.get("name", "").endswith("_bytes_rate"):
                continue
            query = metric.get("query", "")
            if not any(name in query for name in expected_metric_names[protocol]) or "flow_bytes_in" in query or "flow_bytes_out" in query:
                unsupported_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

    assert unsupported_queries == []


def test_flow_metric_files_use_unified_metric_set_and_default_indicators():
    metric_files = _flow_metric_files()

    assert len(metric_files) == len(FLOW_PROTOCOLS) * len(FLOW_OBJECTS)

    for path in metric_files:
        payload = json.loads(path.read_text())
        metric_names = [metric["name"] for metric in payload["metrics"]]

        assert metric_names == FLOW_METRICS
        assert payload["supplementary_indicators"] == FLOW_CORE_METRICS
        assert not OLD_FLOW_METRICS.intersection(metric_names)
        assert not HIGH_CARDINALITY_METRICS.intersection(payload["supplementary_indicators"])
        assert {metric["metric_group"] for metric in payload["metrics"]} == FLOW_GROUPS
        for metric in payload["metrics"]:
            assert metric["instance_id_keys"] == ["instance_id"]


def test_flow_metric_files_do_not_cross_protocol_measurements():
    for path in _flow_metric_files():
        protocol = path.parts[-3]
        payload = json.loads(path.read_text())
        queries = "\n".join(metric["query"] for metric in payload["metrics"])

        if protocol == "netflow":
            assert "sflow_" not in queries
            assert "netflow_" in queries
        else:
            assert "netflow_" not in queries
            assert "sflow_" in queries


def test_flow_direction_label_uses_stable_source_label():
    unstable_direction_queries = []
    missing_stable_direction_queries = []

    for path in _flow_metric_files():
        payload = json.loads(path.read_text())
        for metric in payload["metrics"]:
            query = metric["query"]
            if '"direction"' not in query:
                continue

            if '"direction", "in", "__name__"' in query or '"direction", "out", "__name__"' in query:
                unstable_direction_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

            if '"direction", "in"' in query and '"direction", "in", "instance_id"' not in query:
                missing_stable_direction_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

            if '"direction", "out"' in query and '"direction", "out", "instance_id"' not in query:
                missing_stable_direction_queries.append(f"{path.relative_to(FLOW_METRICS_ROOT)}:{metric['name']}")

    assert unstable_direction_queries == []
    assert missing_stable_direction_queries == []


def test_flow_policy_templates_use_low_cardinality_metrics_only():
    allowed_policy_metrics = {
        "device_flow_bytes_rate",
        "device_flow_packets_rate",
        "device_flow_avg_packet_size",
    }
    policy_files = sorted(
        path
        for protocol in FLOW_PROTOCOLS
        for path in (FLOW_METRICS_ROOT / protocol).glob("*/policy.json")
    )

    assert len(policy_files) == len(FLOW_PROTOCOLS) * len(FLOW_OBJECTS)

    for path in policy_files:
        payload = json.loads(path.read_text())
        metric_names = {template["metric_name"] for template in payload["templates"]}
        assert metric_names
        assert metric_names <= allowed_policy_metrics
        assert not metric_names.intersection(OLD_FLOW_METRICS)
        assert not metric_names.intersection(HIGH_CARDINALITY_METRICS)


def test_flow_metrics_have_bilingual_translations():
    for language in ("zh-Hans", "en"):
        payload = yaml.safe_load((LANGUAGE_ROOT / f"{language}.yaml").read_text(encoding="utf-8"))
        object_metrics = payload["monitor_object_metric"]
        metric_groups = payload["monitor_object_metric_group"]
        plugins = payload["monitor_object_plugin"]

        for object_name in FLOW_MONITOR_OBJECTS:
            missing_metrics = [
                metric_name
                for metric_name in FLOW_METRICS
                if not object_metrics.get(object_name, {}).get(metric_name, {}).get("name")
                or not object_metrics.get(object_name, {}).get(metric_name, {}).get("desc")
            ]
            assert missing_metrics == [], f"{language}:{object_name}: missing metric translations {missing_metrics}"

            missing_groups = [
                group_name
                for group_name in FLOW_GROUPS
                if not metric_groups.get(object_name, {}).get(group_name)
            ]
            assert missing_groups == [], f"{language}:{object_name}: missing group translations {missing_groups}"

        for object_name in FLOW_MONITOR_OBJECTS:
            for protocol_label in ("NetFlow", "sFlow"):
                plugin_name = f"{object_name} Flow {protocol_label}"
                assert plugins.get(plugin_name, {}).get("name"), f"{language}:{plugin_name}: missing plugin name"
                assert plugins.get(plugin_name, {}).get("desc"), f"{language}:{plugin_name}: missing plugin desc"

        language_text = (LANGUAGE_ROOT / f"{language}.yaml").read_text(encoding="utf-8")
        for old_metric in OLD_FLOW_METRICS:
            assert old_metric not in language_text
