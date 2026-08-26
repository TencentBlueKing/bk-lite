"""非内置主机综合监控仪表盘 YAML：可导入、不进内置初始化。"""

from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import YAML_FILE_PATH
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "host_comprehensive_dashboard.yaml"


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def _iter_widgets(view_sets):
    for item in view_sets:
        if item.get("itemType") == "group":
            yield from (item.get("subGridOpts") or {}).get("children") or []
        else:
            yield item


def test_sample_yaml_is_not_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(YAML_FILE_PATH).resolve() != SAMPLE_PATH.resolve()
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("dashboards") or []}
    assert "dashboard::主机综合监控仪表盘" not in builtin_keys


def test_sample_yaml_parses_and_has_no_health_kpi():
    payload = _load_sample()
    document = YAMLDocument(**payload)
    errors = PrecheckService.check_dependencies(document)
    assert errors == []

    dashboard = document.dashboards[0]
    assert dashboard.name == "主机综合监控仪表盘"
    assert dashboard.key == "dashboard::主机综合监控仪表盘"

    groups = dashboard.view_sets
    assert [item["id"] for item in groups] == [
        "group-overview",
        "group-usage",
        "group-top10",
        "group-load-net",
        "group-disk-io",
        "group-write-process",
    ]
    assert [item["name"] for item in groups] == [
        "资源概览",
        "核心使用率",
        "使用率 Top10",
        "负载与流量",
        "磁盘 IO",
        "写入与进程",
    ]
    assert all(item["itemType"] == "group" for item in groups)
    assert [[child["id"] for child in item["subGridOpts"]["children"]] for item in groups] == [
        [
            "host-kpi-count",
            "host-kpi-avg-cpu",
            "host-kpi-avg-memory",
            "host-kpi-avg-disk",
            "host-kpi-max-cpu",
            "host-kpi-max-memory",
        ],
        ["host-trend-cpu", "host-trend-memory", "host-trend-disk"],
        ["host-top-cpu", "host-top-memory", "host-top-disk"],
        ["host-trend-load5", "host-trend-net-in", "host-trend-net-out"],
        [
            "host-trend-disk-io",
            "host-trend-disk-write-latency",
            "host-trend-disk-read-rate",
        ],
        [
            "host-trend-disk-write-rate",
            "host-trend-blocked",
            "host-trend-zombies",
        ],
    ]

    widgets = list(_iter_widgets(groups))
    names = [item["name"] for item in widgets]
    ids = [item["id"] for item in widgets]
    assert len(widgets) == 21
    assert "健康主机" not in names
    assert not any("healthy" in str(item.get("valueConfig", {}).get("selectedFields") or []).lower() for item in widgets)

    assert ids[:6] == [
        "host-kpi-count",
        "host-kpi-avg-cpu",
        "host-kpi-avg-memory",
        "host-kpi-avg-disk",
        "host-kpi-max-cpu",
        "host-kpi-max-memory",
    ]
    assert {item["valueConfig"]["selectedFields"][0] for item in widgets[:6]} == {
        "host_count",
        "avg_cpu",
        "avg_memory",
        "avg_disk",
        "max_cpu",
        "max_memory",
    }

    max_cpu = next(item for item in widgets if item["id"] == "host-kpi-max-cpu")
    assert max_cpu["valueConfig"]["descriptionField"] == "max_cpu_host"
    max_memory = next(item for item in widgets if item["id"] == "host-kpi-max-memory")
    assert max_memory["valueConfig"]["descriptionField"] == "max_memory_host"

    filter_ids = {item["id"] for item in dashboard.filters}
    assert filter_ids == {"instance_ids__string", "time__timeRange"}
    host_filter = next(item for item in dashboard.filters if item["id"] == "instance_ids__string")
    assert host_filter["type"] == "string"
    assert host_filter["inputConfig"]["multiple"] is True
    assert host_filter["inputConfig"]["picker"] == "table"
    assert host_filter["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "monitor/get_host_instance_list"

    for item in widgets:
        bindings = item["valueConfig"]["filterBindings"]
        assert bindings.get("instance_ids__string") is True
        if item["valueConfig"]["chartType"] == "line":
            assert bindings.get("time__timeRange") is True
        else:
            assert "time__timeRange" not in bindings

    line_metrics = [
        next(param["value"] for param in item["valueConfig"]["dataSourceParams"] if param["name"] == "metric_type")
        for item in widgets
        if item["valueConfig"]["chartType"] == "line"
    ]
    assert line_metrics == [
        "cpu",
        "memory",
        "disk",
        "load5",
        "net_in",
        "net_out",
        "disk_io",
        "disk_write_latency",
        "disk_read_rate",
        "disk_write_rate",
        "processes_blocked",
        "processes_zombies",
    ]

    top_metrics = [
        next(param["value"] for param in item["valueConfig"]["dataSourceParams"] if param["name"] == "metric_type")
        for item in widgets
        if item["valueConfig"]["chartType"] == "topN"
    ]
    assert top_metrics == ["cpu", "memory", "disk"]
    for item in widgets:
        if item["valueConfig"]["chartType"] != "topN":
            continue
        metric = next(param for param in item["valueConfig"]["dataSourceParams"] if param["name"] == "metric_type")
        assert metric["inputConfig"]["componentSwitch"] is False

    expected_keys = {
        "监控主机列表::monitor/get_host_instance_list",
        "主机指标趋势::monitor/get_host_metric_range",
        "主机资源快照::monitor/get_host_resource_snapshot",
        "主机资源使用率Top10::monitor/get_host_resource_top",
    }
    assert set(dashboard.refs.datasource_keys) == expected_keys
    assert {item.key for item in document.datasources} == expected_keys
    assert {item.rest_api for item in document.datasources} == {
        "monitor/get_host_instance_list",
        "monitor/get_host_metric_range",
        "monitor/get_host_resource_snapshot",
        "monitor/get_host_resource_top",
    }
