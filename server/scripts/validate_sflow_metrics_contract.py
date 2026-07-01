#!/usr/bin/env python3
import json
import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
TELEGRAF_ROOT = SERVER_ROOT / "apps" / "monitor" / "support-files" / "plugins" / "Telegraf"
SFLOW_ROOT = TELEGRAF_ROOT / "sflow"

PRODUCTION_FRAME_LENGTH = 263
PRODUCTION_EFFECTIVE_SAMPLING_RATE = 2048
PRODUCTION_SFLOW_BYTES = 538624

TRAFFIC_METRICS = {
    "device_flow_bytes_rate": "sflow_bytes",
    "device_flow_packets_rate": "sflow_packets",
    "device_flow_in_bytes_rate": "sflow_bytes",
    "device_flow_out_bytes_rate": "sflow_bytes",
    "device_flow_in_packets_rate": "sflow_packets",
    "device_flow_out_packets_rate": "sflow_packets",
    "device_flow_interface_bytes_rate": "sflow_bytes",
    "device_flow_interface_packets_rate": "sflow_packets",
    "device_flow_top_interfaces_by_bytes": "sflow_bytes",
    "device_flow_protocol_bytes_rate": "sflow_bytes",
    "device_flow_protocol_packets_rate": "sflow_packets",
    "device_flow_dst_port_bytes_rate": "sflow_bytes",
    "device_flow_dst_port_packets_rate": "sflow_packets",
    "device_flow_src_port_bytes_rate": "sflow_bytes",
    "device_flow_top_src_bytes_rate": "sflow_bytes",
    "device_flow_top_dst_bytes_rate": "sflow_bytes",
    "device_flow_top_src_packets_rate": "sflow_packets",
    "device_flow_top_dst_packets_rate": "sflow_packets",
    "device_flow_top_conversation_bytes_rate": "sflow_bytes",
}

ENDPOINT_METRICS = {
    "device_flow_top_src_bytes_rate": "src_ip",
    "device_flow_top_src_packets_rate": "src_ip",
    "device_flow_top_dst_bytes_rate": "dst_ip",
    "device_flow_top_dst_packets_rate": "dst_ip",
}

INTERFACE_METRICS = {
    "device_flow_in_bytes_rate": ("sflow_bytes", ("input_ifindex",)),
    "device_flow_out_bytes_rate": ("sflow_bytes", ("output_ifindex",)),
    "device_flow_in_packets_rate": ("sflow_packets", ("input_ifindex",)),
    "device_flow_out_packets_rate": ("sflow_packets", ("output_ifindex",)),
    "device_flow_interface_bytes_rate": ("sflow_bytes", ("input_ifindex", "output_ifindex")),
    "device_flow_interface_packets_rate": ("sflow_packets", ("input_ifindex", "output_ifindex")),
    "device_flow_top_interfaces_by_bytes": ("sflow_bytes", ("input_ifindex", "output_ifindex")),
}


def _load_metrics(path):
    return json.loads(path.read_text(encoding="utf-8")).get("metrics", [])


def _metric_by_name(metrics):
    return {metric["name"]: metric for metric in metrics}


def _contains_second_pass_sampling(query):
    return "label_value(" in query and (
        '"effective_sampling_rate"' in query or '"sflow_sampling_rate"' in query
    )


def _validate_file(path):
    errors = []
    metrics = _metric_by_name(_load_metrics(path))
    relative_path = path.relative_to(TELEGRAF_ROOT)

    for metric_name, measurement in TRAFFIC_METRICS.items():
        query = metrics.get(metric_name, {}).get("query", "")
        if not query:
            errors.append(f"{relative_path}:{metric_name}: missing metric")
            continue
        if measurement not in query:
            errors.append(f"{relative_path}:{metric_name}: missing {measurement}")
        if _contains_second_pass_sampling(query):
            errors.append(f"{relative_path}:{metric_name}: second-pass sampling normalization")

    avg_packet_query = metrics.get("device_flow_avg_packet_size", {}).get("query", "")
    if "sflow_frame_length" not in avg_packet_query:
        errors.append(f"{relative_path}:device_flow_avg_packet_size: missing sflow_frame_length")

    sampling_query = metrics.get("device_flow_effective_sampling_rate", {}).get("query", "")
    if "sflow_sampling_rate" not in sampling_query and "effective_sampling_rate" not in sampling_query:
        errors.append(f"{relative_path}:device_flow_effective_sampling_rate: missing sampling source")

    for metric_name, label in ENDPOINT_METRICS.items():
        query = metrics.get(metric_name, {}).get("query", "")
        if label not in query:
            errors.append(f"{relative_path}:{metric_name}: missing {label}")
        if "by (instance_id, src)" in query or "by (instance_id, dst)" in query:
            errors.append(f"{relative_path}:{metric_name}: netflow-style endpoint label")

    for metric_name in ("device_flow_protocol_bytes_rate", "device_flow_protocol_packets_rate"):
        query = metrics.get(metric_name, {}).get("query", "")
        if "header_protocol" not in query:
            errors.append(f"{relative_path}:{metric_name}: missing header_protocol")

    conversation_query = metrics.get("device_flow_top_conversation_bytes_rate", {}).get("query", "")
    for label in ("src_ip", "dst_ip", "header_protocol", "dst_port"):
        if label not in conversation_query:
            errors.append(f"{relative_path}:device_flow_top_conversation_bytes_rate: missing {label}")

    for metric_name, expected in INTERFACE_METRICS.items():
        measurement, labels = expected
        query = metrics.get(metric_name, {}).get("query", "")
        if measurement not in query:
            errors.append(f"{relative_path}:{metric_name}: missing {measurement}")
        for label in labels:
            if f'"interface", "$1", "{label}"' not in query:
                errors.append(f"{relative_path}:{metric_name}: missing {label}")

    return errors


def main():
    expected_bytes = PRODUCTION_FRAME_LENGTH * PRODUCTION_EFFECTIVE_SAMPLING_RATE
    if expected_bytes != PRODUCTION_SFLOW_BYTES:
        print(
            "sample check failed: "
            f"{PRODUCTION_FRAME_LENGTH} * {PRODUCTION_EFFECTIVE_SAMPLING_RATE} != {PRODUCTION_SFLOW_BYTES}",
            file=sys.stderr,
        )
        return 1

    paths = sorted(SFLOW_ROOT.glob("*/metrics.json"))
    if not paths:
        print(f"no sFlow metrics files found under {SFLOW_ROOT}", file=sys.stderr)
        return 1

    print("sFlow production metrics contract")
    print(f"sample check: {PRODUCTION_FRAME_LENGTH} * {PRODUCTION_EFFECTIVE_SAMPLING_RATE} = {PRODUCTION_SFLOW_BYTES}")

    all_errors = []
    for path in paths:
        errors = _validate_file(path)
        relative_path = path.relative_to(TELEGRAF_ROOT)
        if errors:
            all_errors.extend(errors)
            print(f"{relative_path}: failed")
        else:
            print(f"{relative_path}: ok - no second-pass sampling normalization")

    if all_errors:
        print("\nErrors:", file=sys.stderr)
        for error in all_errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("production labels: src_ip/dst_ip, header_protocol, input_ifindex/output_ifindex")
    print("BK-Lite labels retained: instance_id, instance_type, collect_type")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
