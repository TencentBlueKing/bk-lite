"""僵尸机报表 YAML：随 init_builtin_canvases 进入内置目录。"""

from pathlib import Path

import yaml

from apps.operation_analysis.management.commands.init_builtin_canvases import (
    YAML_FILE_PATH,
    ZOMBIE_HOST_REPORT_YAML_PATH,
    _get_builtin_canvas_file_paths,
)
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

SUPPORT_DIR = Path(__file__).resolve().parents[1] / "support-files"
SAMPLE_PATH = SUPPORT_DIR / "zombie_host_report.yaml"

ZOMBIE_SOURCE_KEY = "僵尸机查询::monitor/get_zombie_host_report"
SYSTEM_OPTION_KEY = "应用系统::cmdb/list_application_systems"

DEFAULT_THRESHOLDS = {
    "login_min": -1,
    "login_max": 2,
    "packets_recv_max_min": -1,
    "packets_recv_max_max": 200,
    "packets_recv_avg_min": -1,
    "packets_recv_avg_max": 50,
    "cpu_avg_min": -1,
    "cpu_avg_max": 8,
    "cpu_max_min": -1,
    "cpu_max_max": 20,
    "mem_avg_min": -1,
    "mem_avg_max": 25,
    "mem_max_min": -1,
    "mem_max_max": 40,
    "io_max_min": -1,
    "io_max_max": 10,
}

FILTER_PARAM_KEYS = {
    "time",
    "system_uuids",
    "os_type",
    "zombie_whitelist",
    *DEFAULT_THRESHOLDS,
}


def _load_sample():
    return yaml.safe_load(SAMPLE_PATH.read_text(encoding="utf-8"))


def test_zombie_report_yaml_is_loaded_as_builtin():
    assert SAMPLE_PATH.exists()
    assert Path(YAML_FILE_PATH).resolve() != SAMPLE_PATH.resolve()
    assert Path(ZOMBIE_HOST_REPORT_YAML_PATH).resolve() == SAMPLE_PATH.resolve()
    loaded = {Path(path).resolve() for path in _get_builtin_canvas_file_paths()}
    assert SAMPLE_PATH.resolve() in loaded
    builtin = yaml.safe_load(Path(YAML_FILE_PATH).read_text(encoding="utf-8"))
    builtin_keys = {item["key"] for item in builtin.get("reports") or []}
    assert "report::僵尸机报表" not in builtin_keys


def test_zombie_report_yaml_parses_and_binds_table_and_filters():
    payload = _load_sample()
    document = YAMLDocument(**payload)
    errors = PrecheckService.check_dependencies(document)
    assert errors == []

    assert len(document.reports) == 1
    report = document.reports[0]
    assert report.name == "僵尸机报表"
    assert report.key == "report::僵尸机报表"
    assert "时间默认 7 天" in report.desc
    assert "阈值不随窗口缩放" in report.desc
    assert "登录未采集不按 0 过滤" in report.desc

    view_sets = report.view_sets
    sections = view_sets["sections"]
    assert len(sections) == 1
    table = sections[0]
    assert table["id"] == "zombie-table"
    assert table["valueConfig"]["chartType"] == "table"
    assert table["valueConfig"]["dataSource"] == ZOMBIE_SOURCE_KEY

    filter_keys = {item["key"] for item in view_sets["filters"]}
    assert FILTER_PARAM_KEYS <= filter_keys
    number_filters = {item["key"] for item in view_sets["filters"] if item["type"] == "number"}
    assert set(DEFAULT_THRESHOLDS) <= number_filters

    time_filter = next(item for item in view_sets["filters"] if item["key"] == "time")
    assert time_filter["type"] == "timeRange"
    assert time_filter["defaultValue"]["selectValue"] == 10080
    assert time_filter["defaultValue"]["rangePickerVaule"] is None
    assert time_filter["enabled"] is True

    payload_columns = {
        item["key"]: item["title"]
        for item in next(ds["field_schema"] for ds in payload["datasources"] if ds["rest_api"] == "monitor/get_zombie_host_report")
    }
    assert payload_columns["packets_recv_max"] == "入包峰值(pps)"
    assert payload_columns["packets_recv_avg"] == "入包均值(pps)"
    assert payload_columns["cpu_avg"] == "CPU均值(%)"
    assert payload_columns["io_max"] == "IO峰值(%)"

    filter_names = {item["key"]: item["name"] for item in view_sets["filters"]}
    assert filter_names["packets_recv_max_max"] == "入包峰值上限(pps)"
    assert filter_names["cpu_avg_max"] == "CPU均值上限(%)"
    assert filter_names["io_max_max"] == "IO峰值上限(%)"

    inst_filter = next(item for item in view_sets["filters"] if item["key"] == "system_uuids")
    assert inst_filter["type"] == "string"
    assert inst_filter["inputConfig"]["multiple"] is True
    assert inst_filter["inputConfig"]["optionsSource"]["sourceRef"]["value"] == "cmdb/list_application_systems"

    assert set(report.refs.datasource_keys) == {ZOMBIE_SOURCE_KEY, SYSTEM_OPTION_KEY}
    assert {item.key for item in document.datasources} == {ZOMBIE_SOURCE_KEY, SYSTEM_OPTION_KEY}
    assert {item.rest_api for item in document.datasources} == {
        "cmdb/list_application_systems",
        "monitor/get_zombie_host_report",
    }
    assert [item.key for item in document.namespaces] == ["默认命名空间"]


def test_zombie_report_survives_builtin_merge():
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
    keys = {item.key for item in document.reports}
    assert "report::僵尸机报表" in keys
    report = next(item for item in document.reports if item.key == "report::僵尸机报表")
    available = {item.key for item in document.datasources}
    assert set(report.refs.datasource_keys) <= available
    sections = report.view_sets["sections"]
    assert {section["valueConfig"]["dataSource"] for section in sections} <= available
    assert sections[0]["valueConfig"]["dataSource"] == ZOMBIE_SOURCE_KEY
