# -*- coding: utf-8 -*-
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WINDOWS_WMI_METRICS = (
    REPO_ROOT
    / "server/apps/monitor/support-files/plugins/Telegraf/http/windows_wmi/metrics.json"
)


def _load_metrics_by_name():
    with WINDOWS_WMI_METRICS.open(encoding="utf-8") as f:
        metrics = json.load(f)["metrics"]
    return {metric["name"]: metric for metric in metrics}


def test_windows_wmi_metrics_expose_telegraf_aligned_network_rates():
    metrics = _load_metrics_by_name()

    expected = {
        "net_packets_recv_rate": ("net_packets_recv_gauge_value", "cps"),
        "net_packets_sent_rate": ("net_packets_sent_gauge_value", "cps"),
        "net_bytes_recv_rate": ("net_bytes_recv_gauge_value", "byteps"),
        "net_bytes_sent_rate": ("net_bytes_sent_gauge_value", "byteps"),
        "net_err_in_rate": ("net_err_in_gauge_value", "cps"),
        "net_err_out_rate": ("net_err_out_gauge_value", "cps"),
        "net_drop_in_rate": ("net_drop_in_gauge_value", "cps"),
        "net_drop_out_rate": ("net_drop_out_gauge_value", "cps"),
    }

    for metric_name, (source_metric, unit) in expected.items():
        metric = metrics[metric_name]
        assert metric["metric_group"] == "Network"
        assert metric["unit"] == unit
        assert metric["dimensions"] == ["interface"]
        assert metric["query"] == (
            f'rate({source_metric}{{instance_type="os", config_type="windows_wmi", __$labels__}}[5m])'
        )


def test_windows_wmi_metrics_expose_common_host_metric_groups():
    metrics = _load_metrics_by_name()

    for metric_name in [
        "diskio_reads_rate",
        "diskio_write_bytes_rate",
        "processes_running",
        "processes_blocked",
        "processes_zombies",
        "processes_sleeping",
        "system_uptime",
    ]:
        assert metric_name in metrics
