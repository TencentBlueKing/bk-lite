# -*- coding: utf-8 -*-
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = REPO_ROOT / "server/apps/monitor/support-files/plugins/Telegraf/http"
WINDOWS_WMI_METRICS = PLUGIN_ROOT / "windows_wmi/metrics.json"
WINDOWS_WMI_POLICY = PLUGIN_ROOT / "windows_wmi/policy.json"
WINDOWS_WMI_UI = PLUGIN_ROOT / "windows_wmi/UI.json"
HOST_METRICS = PLUGIN_ROOT / "host/metrics.json"
HOST_POLICY = PLUGIN_ROOT / "host/policy.json"
HOST_UI = PLUGIN_ROOT / "host/UI.json"


def _load_json(path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_metrics_by_name(path=WINDOWS_WMI_METRICS):
    return {metric["name"]: metric for metric in _load_json(path)["metrics"]}


def _form_fields_by_name(path):
    return {field["name"]: field for field in _load_json(path)["form_fields"]}


def _policy_templates_by_name(path):
    return {item["name"]: item for item in _load_json(path)["templates"]}


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
        assert metric["dimensions"] == [{"name": "interface"}]
        assert metric["query"] == (f'rate({source_metric}{{instance_type="os", config_type="windows_wmi", __$labels__}}[5m])')


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


def _assert_windows_service_metric(metric, query):
    assert metric["metric_group"] == "Service"
    assert metric["data_type"] == "Enum"
    assert metric["dimensions"] == [{"name": "service"}]
    assert metric["query"] == query
    assert "service_scope" not in json.dumps(metric["dimensions"])


def _assert_windows_service_policy(template, config_type):
    assert template["metric_name"] == "windows_service_state"
    assert template["algorithm"] == "last_over_time"
    assert template["threshold"] == [{"level": "warning", "value": 0, "method": "="}]
    filters = {(item["name"], item["method"], str(item["value"])) for item in template["filter"]}
    assert ("service_scope", "=", "names") in filters
    assert ("config_type", "=", config_type) in filters


def test_windows_wmi_metrics_expose_service_state():
    metric = _load_metrics_by_name()["windows_service_state"]
    _assert_windows_service_metric(
        metric,
        'windows_service_state_gauge_value{instance_type="os", config_type="windows_wmi", __$labels__}',
    )


def test_host_metrics_expose_service_state():
    metric = _load_metrics_by_name(HOST_METRICS)["windows_service_state"]
    _assert_windows_service_metric(
        metric,
        'windows_service_state_gauge{instance_type="os", __$labels__}',
    )


def test_windows_service_policies_only_alert_named_scope():
    wmi_policy = _policy_templates_by_name(WINDOWS_WMI_POLICY)["Windows服务停止"]
    host_policy = _policy_templates_by_name(HOST_POLICY)["Windows服务停止"]
    _assert_windows_service_policy(wmi_policy, "windows_wmi")
    _assert_windows_service_policy(host_policy, "host")


def test_windows_service_ui_defaults_to_none():
    wmi_fields = _form_fields_by_name(WINDOWS_WMI_UI)
    host_fields = _form_fields_by_name(HOST_UI)
    assert wmi_fields["service_scope"]["default_value"] == "none"
    assert host_fields["service_scope"]["default_value"] == "none"
    assert "service" not in wmi_fields["metrics_modules"]["default_value"]
    assert host_fields["service_scope"]["dependency"] == {"field": "os_type", "value": "windows"}
    assert host_fields["service_names"]["dependency"] == {"field": "os_type", "value": "windows"}
