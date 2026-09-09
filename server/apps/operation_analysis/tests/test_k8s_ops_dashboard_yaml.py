"""非内置 K8S 运维仪表盘 YAML：可导入、不进内置初始化。"""

from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import YAML_FILE_PATH
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "k8s_ops_dashboard.yaml"


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def _iter_widgets(view_sets):
    for item in view_sets:
        if item.get("itemType") == "group":
            yield from (item.get("subGridOpts") or {}).get("children") or []
        else:
            yield item


def test_k8s_ops_yaml_is_not_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(YAML_FILE_PATH).resolve() != SAMPLE_PATH.resolve()
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("dashboards") or []}
    assert "dashboard::K8S运维仪表盘" not in builtin_keys


def test_k8s_ops_yaml_parses_and_pins_k8s_alert_source():
    payload = _load_sample()
    document = YAMLDocument(**payload)
    errors = PrecheckService.check_dependencies(document)
    assert errors == []

    dashboard = document.dashboards[0]
    assert dashboard.name == "K8S 运维仪表盘"
    assert dashboard.key == "dashboard::K8S运维仪表盘"

    groups = dashboard.view_sets
    assert [item["id"] for item in groups] == [
        "group-overview",
        "group-alerts",
        "group-trend",
    ]
    assert all(item["itemType"] == "group" for item in groups)

    widgets = list(_iter_widgets(groups))
    by_id = {item["id"]: item for item in widgets}
    assert set(by_id) == {
        "k8s-kpi-pods",
        "k8s-kpi-nodes",
        "k8s-kpi-memory",
        "k8s-kpi-disk",
        "k8s-active-alerts",
        "k8s-trend-memory",
        "k8s-trend-disk",
    }

    alert = by_id["k8s-active-alerts"]
    assert alert["valueConfig"]["chartType"] == "table"
    assert alert["valueConfig"]["dataSource"] == "K8S活跃告警::get_active_alert_top"
    source_id = next(param for param in alert["valueConfig"]["dataSourceParams"] if param["name"] == "source_id")
    assert source_id["value"] == "k8s"
    assert source_id["filterType"] == "fixed"
    assert "filterBindings" not in alert["valueConfig"] or not alert["valueConfig"].get("filterBindings")

    kpi_metrics = [
        next(param["value"] for param in by_id[widget_id]["valueConfig"]["dataSourceParams"] if param["name"] == "metric")
        for widget_id in ("k8s-kpi-pods", "k8s-kpi-nodes", "k8s-kpi-memory", "k8s-kpi-disk")
    ]
    assert kpi_metrics == [
        "cluster_pod_count",
        "cluster_node_count",
        "cluster_memory_utilization",
        "cluster_disk_utilization",
    ]
    for widget_id in ("k8s-kpi-pods", "k8s-kpi-nodes", "k8s-kpi-memory", "k8s-kpi-disk"):
        bindings = by_id[widget_id]["valueConfig"]["filterBindings"]
        assert bindings.get("instance_ids__string") is True
        assert bindings.get("time__timeRange") is True

    cluster_filter = next(item for item in dashboard.filters if item["id"] == "instance_ids__string")
    assert cluster_filter["inputConfig"]["multiple"] is False
    assert cluster_filter["defaultValue"] in ("", None)
    assert cluster_filter["inputConfig"]["optionsSource"]["sourceRef"]["value"] == ("K8S集群实例::monitor/get_monitor_instance_list")
    for widget_id in ("k8s-kpi-pods", "k8s-kpi-nodes", "k8s-kpi-memory", "k8s-kpi-disk", "k8s-trend-memory", "k8s-trend-disk"):
        instance_ids = next(param for param in by_id[widget_id]["valueConfig"]["dataSourceParams"] if param["name"] == "instance_ids")
        assert instance_ids["inputConfig"]["multiple"] is False
        assert instance_ids["value"] in ("", None)
        assert not isinstance(instance_ids["value"], list)

    expected_keys = {
        "K8S集群实例::monitor/get_monitor_instance_list",
        "K8S集群指标快照::monitor/query_metric_series",
        "K8S集群指标趋势::monitor/query_metric_series",
        "K8S活跃告警::get_active_alert_top",
    }
    assert set(dashboard.refs.datasource_keys) == expected_keys
    assert {item.key for item in document.datasources} == expected_keys
    assert {item.rest_api for item in document.datasources} == {
        "monitor/get_monitor_instance_list",
        "monitor/query_metric_series",
        "get_active_alert_top",
    }

    instance_source = next(item for item in document.datasources if item.name == "K8S集群实例")
    object_names = next(param for param in instance_source.params if param["name"] == "object_names")
    assert object_names["value"] == ["Cluster"]
    assert object_names["filterType"] == "fixed"

    alert_source = next(item for item in document.datasources if item.key == "K8S活跃告警::get_active_alert_top")
    assert alert_source.rest_api == "get_active_alert_top"
    alert_source_id = next(param for param in alert_source.params if param["name"] == "source_id")
    assert alert_source_id["value"] == "k8s"
    assert alert_source_id["filterType"] == "fixed"
    assert "alert/get_active_alert_top" not in {item.rest_api for item in document.datasources}
