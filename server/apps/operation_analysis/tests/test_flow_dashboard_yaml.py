"""Flow 仪表盘 YAML：随 init_builtin_canvases 进入内置目录。"""

from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import FLOW_DASHBOARD_YAML_PATH, YAML_FILE_PATH, _get_builtin_canvas_file_paths
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "flow_dashboard.yaml"


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def _iter_widgets(view_sets):
    for item in view_sets:
        if item.get("itemType") == "group":
            yield from (item.get("subGridOpts") or {}).get("children") or []
        else:
            yield item


def test_flow_yaml_is_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(YAML_FILE_PATH).resolve() != SAMPLE_PATH.resolve()
    assert Path(FLOW_DASHBOARD_YAML_PATH).resolve() == SAMPLE_PATH.resolve()
    loaded = {Path(path).resolve() for path in _get_builtin_canvas_file_paths()}
    assert SAMPLE_PATH.resolve() in loaded
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("dashboards") or []}
    assert "dashboard::Flow网络流量分析仪表盘" not in builtin_keys
    flow = yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))
    assert "dashboard::Flow网络流量分析仪表盘" in {item["key"] for item in flow.get("dashboards") or []}


def test_sample_yaml_parses_and_binds_flow_sources():
    payload = _load_sample()
    document = YAMLDocument(**payload)
    errors = PrecheckService.check_dependencies(document)
    assert errors == []

    dashboard = document.dashboards[0]
    assert dashboard.name == "Flow 网络流量分析仪表盘"
    assert dashboard.key == "dashboard::Flow网络流量分析仪表盘"

    groups = dashboard.view_sets
    assert [item["id"] for item in groups] == [
        "group-overview",
        "group-trend",
        "group-rank",
        "group-conversation",
        "group-node-graph",
    ]
    assert all(item["itemType"] == "group" for item in groups)

    widgets = list(_iter_widgets(groups))
    by_id = {item["id"]: item for item in widgets}
    assert set(by_id) == {
        "flow-kpi-bytes",
        "flow-kpi-packets",
        "flow-kpi-avg-size",
        "flow-kpi-sampling",
        "flow-trend-bytes",
        "flow-trend-packets",
        "flow-trend-protocol",
        "flow-pie-protocol",
        "flow-topn",
        "flow-table-conversation",
        "flow-node-graph-ip",
        "flow-node-graph-service",
    }
    assert by_id["flow-kpi-bytes"]["valueConfig"]["chartType"] == "single"
    assert by_id["flow-kpi-bytes"]["valueConfig"]["unitId"] == "bps"
    assert by_id["flow-kpi-bytes"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-trend-bytes"]["valueConfig"]["unitId"] == "bps"
    assert by_id["flow-trend-bytes"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-trend-protocol"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-pie-protocol"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-topn"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-table-conversation"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-node-graph-ip"]["valueConfig"]["conversionFactor"] == 8
    assert by_id["flow-kpi-avg-size"]["valueConfig"]["unitId"] == "bytesIEC"

    assert by_id["flow-trend-bytes"]["valueConfig"]["chartType"] == "line"
    assert by_id["flow-pie-protocol"]["valueConfig"]["chartType"] == "pie"
    assert by_id["flow-topn"]["valueConfig"]["chartType"] == "topN"
    assert by_id["flow-table-conversation"]["valueConfig"]["chartType"] == "table"
    assert by_id["flow-node-graph-ip"]["valueConfig"]["chartType"] == "nodeGraph"
    assert by_id["flow-node-graph-ip"]["valueConfig"]["nodeGraphIdentityMode"] == "ip"
    assert by_id["flow-node-graph-ip"]["valueConfig"]["nodeGraphSourceField"] == "src"
    assert by_id["flow-node-graph-ip"]["valueConfig"]["nodeGraphTargetField"] == "dst"
    assert by_id["flow-node-graph-ip"]["valueConfig"]["nodeGraphValueField"] == "value"
    assert by_id["flow-node-graph-service"]["valueConfig"]["chartType"] == "nodeGraph"
    assert by_id["flow-node-graph-service"]["valueConfig"]["nodeGraphIdentityMode"] == "service"
    assert by_id["flow-node-graph-service"]["valueConfig"]["nodeGraphTargetPortField"] == "dst_port"

    host_filter = next(item for item in dashboard.filters if item["id"] == "instance_ids__string")
    assert host_filter["inputConfig"]["multiple"] is True
    assert host_filter["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "monitor/get_monitor_instance_list"

    for item in widgets:
        bindings = item["valueConfig"]["filterBindings"]
        assert bindings.get("instance_ids__string") is True
        assert bindings.get("time__timeRange") is True

    topn_metric = next(param for param in by_id["flow-topn"]["valueConfig"]["dataSourceParams"] if param["name"] == "metric")
    assert topn_metric["inputConfig"]["componentSwitch"] is True
    assert {item["value"] for item in topn_metric["inputConfig"]["optionsSource"]["staticItems"]} == {
        "device_flow_top_src_bytes_rate",
        "device_flow_top_dst_bytes_rate",
        "device_flow_top_src_ip_port_bytes_rate",
        "device_flow_top_dst_ip_port_bytes_rate",
        "device_flow_protocol_bytes_rate",
    }
    assert "device_flow_dst_port_bytes_rate" not in {item["value"] for item in topn_metric["inputConfig"]["optionsSource"]["staticItems"]}

    expected_keys = {
        "监控实例列表::monitor/get_monitor_instance_list",
        "受控指标趋势::monitor/query_metric_series",
        "受控指标排行::monitor/query_metric_series",
    }
    assert set(dashboard.refs.datasource_keys) == expected_keys
    assert {item.key for item in document.datasources} == expected_keys
    assert {item.rest_api for item in document.datasources} == {
        "monitor/get_monitor_instance_list",
        "monitor/query_metric_series",
    }
    assert {item.name for item in document.datasources} == {
        "监控实例列表（选项）",
        "受控指标趋势",
        "受控指标排行",
    }
    assert [item.key for item in document.namespaces] == ["默认命名空间"]


def test_flow_dashboard_survives_builtin_merge():
    from apps.operation_analysis.management.commands.init_builtin_canvases import (
        _get_builtin_canvas_file_paths,
        _load_source_api_document,
        _merge_yaml_documents,
    )

    documents = [_load_source_api_document()]
    for file_path in _get_builtin_canvas_file_paths():
        documents.append(yaml.safe_load(Path(file_path).read_text(encoding="utf-8")))
    merged = _merge_yaml_documents(documents)
    document = YAMLDocument(**merged)
    keys = {item.key for item in document.dashboards}
    assert "dashboard::Flow网络流量分析仪表盘" in keys
    flow = next(item for item in document.dashboards if item.key == "dashboard::Flow网络流量分析仪表盘")
    assert flow.name == "Flow 网络流量分析仪表盘"
    widget_ids = {item["id"] for item in _iter_widgets(flow.view_sets)}
    assert "flow-node-graph-ip" in widget_ids
    assert "flow-topn" in widget_ids
