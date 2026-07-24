"""K3S 插件、采集清单与前端查询的纵向指标契约。"""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PLUGIN = ROOT / "server/apps/monitor/support-files/plugins/unknown/k3s/k3s/metrics.json"
MANIFEST = ROOT / "agents/webhookd/bk-lite-k3s-metric-collector.yaml"
DASHBOARDS = ROOT / "web/src/app/monitor/dashboards/objects"
MEASUREMENT_RE = re.compile(r"prometheus_remote_write_([A-Za-z0-9_]+)")

CADVISOR = {
    "container_cpu_usage_seconds_total",
    "container_memory_working_set_bytes",
    "container_fs_reads_total",
    "container_fs_writes_total",
    "container_network_receive_bytes_total",
    "container_network_transmit_bytes_total",
}
KSM = {
    "kube_daemonset_status_desired_number_scheduled",
    "kube_daemonset_status_number_available",
    "kube_daemonset_status_number_unavailable",
    "kube_deployment_spec_replicas",
    "kube_deployment_status_replicas_available",
    "kube_deployment_status_replicas_unavailable",
    "kube_node_info",
    "kube_node_status_allocatable",
    "kube_node_status_condition",
    "kube_pod_container_resource_limits",
    "kube_pod_container_resource_requests",
    "kube_pod_container_status_restarts_total",
    "kube_pod_container_status_waiting_reason",
    "kube_pod_info",
    "kube_pod_status_phase",
    "kube_statefulset_replicas",
    "kube_statefulset_status_replicas_ready",
}
TELEGRAF = {
    "cpu_usage_idle",
    "cpu_usage_iowait",
    "cpu_usage_system",
    "cpu_usage_user",
    "disk_free",
    "disk_inodes_used_percent",
    "disk_total",
    "disk_used",
    "disk_used_percent",
    "diskio_io_util",
    "diskio_read_bytes",
    "diskio_read_time",
    "diskio_reads",
    "diskio_write_bytes",
    "diskio_write_time",
    "diskio_writes",
    "mem_available",
    "mem_buffered",
    "mem_cached",
    "mem_shared",
    "mem_swap_free",
    "mem_total",
    "mem_used",
    "mem_used_percent",
    "net_bytes_recv",
    "net_bytes_sent",
    "net_packets_recv",
    "net_packets_sent",
    "system_load1",
    "system_load5",
    "system_load15",
}


def _measurements(text):
    measurements = set(MEASUREMENT_RE.findall(text))
    measurements.update(
        metric
        for metric in TELEGRAF
        if re.search(rf"\b{re.escape(metric)}\s*\{{", text)
    )
    return measurements


def test_manifest_allowlists_match_declared_producers():
    manifest = MANIFEST.read_text(encoding="utf-8")
    allowlists = [
        set(value.split("|"))
        for value in re.findall(r"regex: ([a-z0-9_|]+)", manifest)
        if "container_" in value or "kube_" in value
    ]

    assert CADVISOR in allowlists
    assert KSM in allowlists
    assert all(f"[[inputs.{name}]]" in manifest for name in (
        "cpu", "disk", "diskio", "mem", "net", "system"
    ))


def test_plugin_and_dashboards_only_query_k3s_produced_measurements():
    plugin_text = PLUGIN.read_text(encoding="utf-8")
    plugin = json.loads(plugin_text)
    dashboard_text = "\n".join(
        path.read_text(encoding="utf-8")
        for directory in ("k3s-cluster", "k3s-node", "k3s-pod")
        for path in (DASHBOARDS / directory).rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    produced = CADVISOR | KSM | TELEGRAF

    assert _measurements(plugin_text) <= produced
    assert _measurements(dashboard_text) <= produced
    assert all(
        f"prometheus_remote_write_{metric}" not in plugin_text
        and f"prometheus_remote_write_{metric}" not in dashboard_text
        for metric in TELEGRAF
    )
    plugin_queries = [plugin["status_query"]]
    for monitor_object in plugin["objects"]:
        plugin_queries.append(monitor_object["default_metric"])
        plugin_queries.extend(metric["query"] for metric in monitor_object["metrics"])
    assert all(
        'instance_type="k3s"' in query or "instance_type='k3s'" in query
        for query in plugin_queries
    )
    assert all(
        'instance_type="k8s"' not in query and "instance_type='k8s'" not in query
        for query in plugin_queries
    )
    assert 'instance_type="k3s"' in dashboard_text
    assert 'instance_type="k8s"' not in dashboard_text


def test_plugin_identity_matches_manifest_identity():
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    manifest = MANIFEST.read_text(encoding="utf-8")

    assert plugin["plugin"] == "K3S"
    assert {item["name"] for item in plugin["objects"]} == {
        "K3SCluster",
        "K3SNode",
        "K3SPod",
    }
    assert 'instance_type = "k3s"' in manifest
    assert 'instance_type = "k8s"' not in manifest
