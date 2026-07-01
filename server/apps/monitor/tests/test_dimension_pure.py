"""dimension 工具纯函数测试 — 维度构建/解析/格式化的真实行为及异常契约。"""
import base64

import pytest

from apps.monitor.utils.dimension import (
    build_safe_instance_id,
    build_dimensions,
    extract_monitor_instance_id,
    format_dimension_str,
    build_metric_template_vars,
    parse_instance_id,
    normalize_instance_identity,
    format_dimension_value,
)

pytestmark = pytest.mark.unit


def test_build_safe_instance_id_is_decodable():
    sid = build_safe_instance_id("vc-a", "host-1")
    padded = sid + "=" * (-len(sid) % 4)
    assert base64.urlsafe_b64decode(padded).decode() == "vc-a:host-1"


def test_build_safe_instance_id_rejects_empty_part():
    with pytest.raises(ValueError, match="must not be empty"):
        build_safe_instance_id("a", "  ")


def test_build_dimensions_no_keys_returns_empty():
    assert build_dimensions(("h1",), None) == {}


def test_build_dimensions_from_tuple():
    assert build_dimensions(("h1", "eth0"), ["instance_id", "device"]) == {
        "instance_id": "h1",
        "device": "eth0",
    }


def test_build_dimensions_from_str_tuple():
    assert build_dimensions("('h1', 'eth0')", ["instance_id", "device"]) == {
        "instance_id": "h1",
        "device": "eth0",
    }


def test_build_dimensions_bad_str_returns_empty():
    assert build_dimensions("not-a-tuple", ["instance_id"]) == {}


def test_build_dimensions_zips_to_shorter_length():
    assert build_dimensions(("h1",), ["instance_id", "device"]) == {"instance_id": "h1"}


def test_extract_monitor_instance_id_from_multidim():
    assert extract_monitor_instance_id(("vc-a", "host-1")) == "('vc-a',)"


def test_extract_monitor_instance_id_unparseable_str_returns_input():
    assert extract_monitor_instance_id("plain") == "plain"


def test_format_dimension_str_excludes_first_key():
    dims = {"instance_id": "h1", "device": "eth0", "mount": "/home"}
    out = format_dimension_str(dims, ["instance_id", "device", "mount"])
    assert out == "device:eth0, mount:/home"


def test_format_dimension_str_only_first_key_returns_empty():
    assert format_dimension_str({"instance_id": "h1"}, ["instance_id"]) == ""


def test_format_dimension_str_empty():
    assert format_dimension_str({}, ["instance_id"]) == ""


def test_build_metric_template_vars_prefix():
    assert build_metric_template_vars({"device": "eth0"}) == {"metric__device": "eth0"}


@pytest.mark.parametrize("value,expected", [
    (("a", "b"), ("a", "b")),
    (["a", "b"], ("a", "b")),
    ("('a', 'b')", ("a", "b")),
    ("['a', 'b']", ("a", "b")),
    ("123", (123,)),
    ("plain", ("plain",)),
    (42, (42,)),
])
def test_parse_instance_id_variants(value, expected):
    assert parse_instance_id(value) == expected


@pytest.mark.parametrize("bad", [None, ""])
def test_normalize_instance_identity_empty_raises(bad):
    with pytest.raises(ValueError, match="instance_id is required"):
        normalize_instance_identity(bad)


def test_normalize_instance_identity_single_dim():
    res = normalize_instance_identity("abc123")
    assert res["logical_instance_value"] == "abc123"
    assert res["storage_instance_key"] == "('abc123',)"
    assert res["raw_input"] == "abc123"


def test_normalize_instance_identity_multi_dim_keeps_full_tuple():
    res = normalize_instance_identity("('vc-a', 'host-1')")
    assert res["logical_instance_value"] == "vc-a"
    assert res["storage_instance_key"] == "('vc-a', 'host-1')"


def test_normalize_instance_identity_invalid_first_empty_raises():
    with pytest.raises(ValueError, match="invalid instance_id"):
        normalize_instance_identity("('', 'x')")


def test_format_dimension_value_default_order():
    assert format_dimension_value({"a": "1", "b": "2"}) == "a:1,b:2"


def test_format_dimension_value_ordered_keys_and_name_map():
    out = format_dimension_value(
        {"device": "eth0", "mount": "/"},
        ordered_keys=["mount", "device"],
        name_map={"device": "网卡"},
    )
    assert out == "mount:/,网卡:eth0"


def test_format_dimension_value_none_value_kept_empty():
    assert format_dimension_value({"k": None}) == "k:"


def test_format_dimension_value_skips_missing_ordered_key():
    assert format_dimension_value({"a": "1"}, ordered_keys=["a", "missing"]) == "a:1"


def test_format_dimension_value_empty_dict():
    assert format_dimension_value({}) == ""
