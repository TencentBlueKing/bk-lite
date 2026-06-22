import json
from pathlib import Path

import pytest
import yaml


PLUGIN_DIR = (
    Path(__file__).resolve().parents[1]
    / "support-files"
    / "plugins"
    / "Telegraf"
    / "web"
    / "web"
)
LANGUAGE_DIR = Path(__file__).resolve().parents[1] / "language"
RESULT_CODE_VALUES = {
    0: "成功",
    1: "响应内容不匹配",
    2: "响应体读取失败",
    3: "连接失败",
    4: "超时",
    5: "DNS错误",
    6: "响应状态码不匹配",
}


@pytest.fixture(scope="module")
def metrics():
    return json.loads((PLUGIN_DIR / "metrics.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ui():
    return json.loads((PLUGIN_DIR / "UI.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def toml_text():
    return (PLUGIN_DIR / "http_response.child.toml.j2").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def languages():
    return {
        lang: yaml.safe_load((LANGUAGE_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        for lang in ("zh-Hans", "en")
    }


@pytest.mark.unit
def test_website_status_query_only_treats_successful_probes_as_normal(metrics):
    query = metrics["status_query"]

    assert "http_response_result_type" in query
    assert "result='success'" in query
    assert "instance_type='web'" in query
    assert "collect_type='web'" in query


@pytest.mark.unit
def test_website_success_rate_keeps_failed_probes_as_zero(metrics):
    success_rate = {item["name"]: item for item in metrics["metrics"]}["http_node_success_rate"]
    query = success_rate["query"]

    assert "sum without (result)" in query
    assert " or " in query
    assert '* 0' in query


@pytest.mark.unit
def test_website_exposes_probe_result_code_as_first_list_metric(metrics):
    result_code = {item["name"]: item for item in metrics["metrics"]}["http_response_result_code"]
    enum_values = {item["id"]: item["name"] for item in json.loads(result_code["unit"])}
    first_display_field = sorted(metrics["display_fields"], key=lambda item: item["sort_order"])[0]

    assert result_code["query"] == "http_response_result_code{__$labels__}"
    assert result_code["data_type"] == "Enum"
    assert enum_values == RESULT_CODE_VALUES
    assert first_display_field["name"] == "Probe Result"
    assert first_display_field["metrics"] == [{"plugin": "Website", "metric": "http_response_result_code"}]


@pytest.mark.unit
def test_website_probe_result_code_has_language_entries(languages):
    zh_metric = languages["zh-Hans"]["monitor_object_metric"]["Website"]["http_response_result_code"]
    en_metric = languages["en"]["monitor_object_metric"]["Website"]["http_response_result_code"]

    assert zh_metric["name"] == "拨测结果"
    assert "result_code" in en_metric["desc"]
    assert en_metric["name"] == "Probe Result"


@pytest.mark.unit
def test_website_https_probe_can_opt_into_skipping_certificate_verification(ui, toml_text):
    fields = {field["name"]: field for field in ui["table_columns"]}

    assert fields["insecure_skip_verify"]["type"] == "switch"
    assert fields["insecure_skip_verify"]["default_value"] is False
    assert "insecure_skip_verify = {{ insecure_skip_verify | default(false) | lower }}" in toml_text
