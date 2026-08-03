import json
import re
from pathlib import Path

import pytest
import yaml

from apps.core.utils.loader import LanguageLoader

from apps.monitor.services.website_config import normalize_website_request_config
from apps.monitor.utils.plugin_controller import Controller


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
        lang: LanguageLoader("monitor", lang).translations
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
    form_fields = {field["name"]: field for field in ui["form_fields"]}
    insecure_skip_verify = form_fields["insecure_skip_verify"]

    assert insecure_skip_verify["type"] == "switch"
    assert insecure_skip_verify["default_value"] is False
    assert "visible_in" not in insecure_skip_verify
    assert "insecure_skip_verify" not in fields
    assert "insecure_skip_verify = {{ insecure_skip_verify | default(false) | lower }}" in toml_text


@pytest.mark.unit
def test_website_url_rule_accepts_bracketed_ipv6_literals(ui):
    url_field = {field["name"]: field for field in ui["table_columns"]}["url"]
    pattern = url_field["rules"][0]["pattern"]

    assert url_field["label"] == "URL（IPv4/IPv6）"
    assert url_field["widget_props"]["placeholder"] == "https://example.com 或 https://[2001:db8::1]/"
    assert re.fullmatch(pattern, "http://[2001:db8::1]/")
    assert re.fullmatch(pattern, "https://[2001:db8::1]:8443/health")
    assert re.fullmatch(pattern, "2001:db8::1") is None


@pytest.mark.unit
def test_website_auto_access_columns_have_compact_layout(ui):
    fields = {field["name"]: field for field in ui["table_columns"]}

    assert fields["node_ids"]["widget_props"]["width"] == 220
    assert fields["url"]["widget_props"]["width"] == 420
    assert fields["instance_name"]["widget_props"]["width"] == 220
    assert fields["group_ids"]["widget_props"]["width"] == 220


@pytest.mark.unit
def test_website_ignores_empty_key_value_placeholders():
    normalized = normalize_website_request_config(
        {
            "url": "https://www.baidu.com/",
            "request_params": [{"key": "", "value": ""}, {"key": "tag", "value": "blue"}],
            "request_headers": [{"key": "", "value": ""}],
        }
    )

    assert normalized["request_params"] == [{"key": "tag", "value": "blue"}]
    assert normalized["request_headers"] == []
    assert normalized["request_url"] == "https://www.baidu.com/?tag=blue"


@pytest.mark.unit
def test_website_exposes_advanced_http_request_configuration(ui, metrics):
    fields = {field["name"]: field for field in ui["form_fields"]}
    result_code = {item["name"]: item for item in metrics["metrics"]}["http_response_result_code"]
    enum_values = {item["id"]: item["name"] for item in json.loads(result_code["unit"])}

    assert fields["request_method"]["options"] == [
        {"label": "GET", "value": "GET"},
        {"label": "HEAD", "value": "HEAD"},
        {"label": "POST", "value": "POST"},
    ]
    assert fields["request_body"]["dependency"] == {"field": "request_method", "value": "POST"}
    assert fields["request_params"]["type"] == "key_value_list"
    assert fields["request_params"]["section"] == "request"
    assert fields["auth_type"]["section"] == "auth"
    assert fields["response_status_code"]["section"] == "response"
    assert fields["insecure_skip_verify"]["section"] == "tls"
    for name in (
        "monitor_url",
        "interval",
        "request_method",
        "request_body",
        "request_params",
        "request_headers",
        "auth_type",
        "username",
        "ENV_PASSWORD",
        "ENV_BEARER_TOKEN",
        "response_status_code",
        "response_string_match",
        "response_timeout",
        "follow_redirects",
        "insecure_skip_verify",
    ):
        assert fields[name].get("guide_short"), f"{name} missing guide_short"
    assert fields["request_headers"]["type"] == "key_value_list"
    assert fields["auth_type"]["options"] == [
        {"label": "无认证", "value": "none"},
        {"label": "Basic Auth", "value": "basic"},
        {"label": "Bearer Token", "value": "bearer"},
    ]
    assert fields["response_status_code"]["advanced"] is True
    assert fields["response_string_match"]["advanced"] is True
    assert enum_values[1] == "响应内容不匹配"
    assert enum_values[6] == "响应状态码不匹配"
    assert metrics.get("support_collect_detect") is False


@pytest.mark.unit
def test_website_template_renders_configured_telegraf_http_response_options(toml_text):
    rendered = Controller({}).render_template(
        toml_text,
        {
            "url": "https://example.com/health",
            "request_url": "https://example.com/health?region=%E4%B8%8A%E6%B5%B7&tag=blue&tag=green",
            "interval": 60,
            "insecure_skip_verify": False,
            "request_method": "POST",
            "request_body": '{"source":"bk-lite"}',
            "request_headers": [
                {"key": "Content-Type", "value": 'application/json; charset="utf-8"'},
            ],
            "auth_type": "bearer",
            "response_status_code": 201,
            "response_string_match": '"ok":true',
            "response_timeout": 15,
            "follow_redirects": False,
            "instance_id": "web_example",
            "instance_type": "web",
            "config_id": "WEBSITE",
        },
        escape_toml_strings=True,
    )

    assert 'urls = ["https://example.com/health?region=%E4%B8%8A%E6%B5%B7&tag=blue&tag=green"]' in rendered
    assert 'method = "POST"' in rendered
    assert 'body = "{\\"source\\":\\"bk-lite\\"}"' in rendered
    assert 'response_status_code = 201' in rendered
    assert 'response_string_match = "\\"ok\\":true"' in rendered
    assert 'response_timeout = "15s"' in rendered
    assert "follow_redirects = false" in rendered
    assert '"Content-Type" = "application/json; charset=\\"utf-8\\""' in rendered
    assert 'Authorization = "Bearer ${BEARER_TOKEN__WEBSITE}"' in rendered
