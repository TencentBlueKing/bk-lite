# -*- coding: utf-8 -*-
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
HOST_REMOTE_METRICS = (
    REPO_ROOT
    / "server/apps/monitor/support-files/plugins/Telegraf/http/host/metrics.json"
)


def _load_metrics_by_name():
    with HOST_REMOTE_METRICS.open(encoding="utf-8") as f:
        metrics = json.load(f)["metrics"]
    return {metric["name"]: metric for metric in metrics}


def test_host_remote_network_metrics_expose_telegraf_rate_semantics():
    metrics = _load_metrics_by_name()

    expected = {
        "net_packets_recv_rate": ("net_packets_recv_gauge", "cps"),
        "net_packets_sent_rate": ("net_packets_sent_gauge", "cps"),
        "net_bytes_recv_rate": ("net_bytes_recv_gauge", "byteps"),
        "net_bytes_sent_rate": ("net_bytes_sent_gauge", "byteps"),
        "net_err_in_rate": ("net_err_in_gauge", "cps"),
        "net_err_out_rate": ("net_err_out_gauge", "cps"),
        "net_drop_in_rate": ("net_drop_in_gauge", "cps"),
        "net_drop_out_rate": ("net_drop_out_gauge", "cps"),
    }

    for metric_name, (source_metric, unit) in expected.items():
        metric = metrics[metric_name]
        assert metric["metric_group"] == "Network"
        assert metric["unit"] == unit
        assert metric["dimensions"] == ["interface"]
        assert metric["query"] == (
            f'rate({source_metric}{{instance_type="os", __$labels__}}[5m])'
        )
