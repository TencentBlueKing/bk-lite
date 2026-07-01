"""ConfigFormat 纯函数测试 — toml/json/yaml/url 互转的真实往返行为。"""
import pytest

from apps.monitor.utils.config_format import ConfigFormat

pytestmark = pytest.mark.unit


def test_toml_to_dict_extracts_plugin_and_config():
    toml_config = """
[[inputs.cpu]]
percpu = true
totalcpu = false
"""
    result = ConfigFormat.toml_to_dict(toml_config)
    assert result["plugin"] == ("inputs", "cpu")
    assert result["config"] == {"percpu": True, "totalcpu": False}


def test_json_to_toml_roundtrip():
    json_config = {"plugin": ("inputs", "cpu"), "config": {"percpu": True}}
    toml_text = ConfigFormat.json_to_toml(json_config)
    assert "[inputs.cpu]" in toml_text
    assert "percpu = true" in toml_text
    # 往返回字典
    back = ConfigFormat.toml_to_dict(toml_text)
    assert back["plugin"] == ("inputs", "cpu")
    assert back["config"] == {"percpu": True}


def test_yaml_to_dict():
    assert ConfigFormat.yaml_to_dict("a: 1\nb: two") == {"a": 1, "b": "two"}


def test_json_to_yaml_roundtrip():
    data = {"x": [1, 2], "y": "z"}
    yaml_text = ConfigFormat.json_to_yaml(data)
    assert ConfigFormat.yaml_to_dict(yaml_text) == data


def test_query_params_to_url_and_back():
    base = "http://example.com/api"
    url = ConfigFormat.query_params_to_url(base, {"a": "1", "b": "2"})
    assert url.startswith(base + "?")
    parsed = ConfigFormat.extract_query_params(url)
    assert parsed == {"a": "1", "b": "2"}


def test_extract_query_params_collapses_single_and_keeps_multi():
    url = "http://h/x?one=1&many=a&many=b"
    parsed = ConfigFormat.extract_query_params(url)
    assert parsed["one"] == "1"
    assert parsed["many"] == ["a", "b"]


def test_query_params_to_url_doseq_for_list():
    url = ConfigFormat.query_params_to_url("http://h", {"k": ["a", "b"]})
    assert "k=a" in url and "k=b" in url
