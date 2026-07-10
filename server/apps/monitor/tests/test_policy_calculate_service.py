"""policy_calculate 测试 — VM 结果转 DataFrame 与阈值告警计算的真实逻辑。"""

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.tasks.utils.policy_calculate import (
    vm_to_dataframe,
    _format_value_with_unit,
    calculate_alerts,
)

pytestmark = pytest.mark.unit


def _vm_rows():
    return [
        {"metric": {"instance_id": "h1", "device": "eth0"}, "values": [[1, "10"], [2, "20"]]},
        {"metric": {"instance_id": "h2", "device": "eth1"}, "values": [[1, "1"], [2, "2"]]},
    ]


def test_vm_to_dataframe_default_instance_id_col():
    df = vm_to_dataframe(_vm_rows())
    assert list(df["instance_id"]) == [("h1",), ("h2",)]


def test_vm_to_dataframe_with_instance_id_keys():
    df = vm_to_dataframe(_vm_rows(), instance_id_keys=["instance_id", "device"])
    assert list(df["instance_id"]) == [("h1", "eth0"), ("h2", "eth1")]


def test_format_value_none_returns_na():
    assert _format_value_with_unit(None, "%") == "N/A"


def test_format_value_enum_mapping_hit():
    assert _format_value_with_unit(1.0, "", {1: "在线"}) == "在线"


def test_format_value_enum_mapping_miss_falls_back_to_number():
    assert _format_value_with_unit(3.0, "%", {1: "在线"}) == "3.00%"


def test_format_value_with_unit_two_decimals():
    assert _format_value_with_unit(12.345, "MB") == "12.35MB"


def test_format_value_without_unit():
    assert _format_value_with_unit(5, "") == "5.00"


def test_calculate_alerts_triggers_above_threshold():
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "90"], [2, "95"]]},
        ]
    )
    thresholds = [{"method": ">", "value": 80, "level": "error"}]
    ctx = {
        "instance_id_keys": ["instance_id"],
        "monitor_object": "Host",
        "metric_name": "cpu",
        "display_unit": "%",
        "instances_map": {"('h1',)": "主机1"},
    }
    alerts, infos = calculate_alerts("$instance_name $value", df, thresholds, ctx, n=2)
    assert len(alerts) == 1
    assert infos == []
    a = alerts[0]
    assert a["level"] == "error"
    assert a["value"] == 95.0
    assert a["monitor_instance_id"] == "('h1',)"
    assert "主机1" in a["content"] and "95.00%" in a["content"]


def test_calculate_alerts_below_threshold_goes_to_info():
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "10"], [2, "20"]]},
        ]
    )
    thresholds = [{"method": ">", "value": 80, "level": "error"}]
    ctx = {"instance_id_keys": ["instance_id"]}
    alerts, infos = calculate_alerts("x", df, thresholds, ctx, n=2)
    assert alerts == []
    assert len(infos) == 1
    assert infos[0]["level"] == "info"
    assert infos[0]["value"] == "20"


@pytest.mark.parametrize("bad_value", ["inf", "-inf", "nan"])
def test_calculate_alerts_skips_non_finite_values(bad_value):
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "90"], [2, bad_value]]},
        ]
    )
    thresholds = [{"method": ">", "value": 80, "level": "error"}]
    alerts, infos = calculate_alerts("x", df, thresholds, {"instance_id_keys": ["instance_id"]}, n=2)

    assert alerts == []
    assert infos == []


def test_calculate_alerts_skips_rows_with_insufficient_values():
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "90"]]},
        ]
    )
    thresholds = [{"method": ">", "value": 80, "level": "error"}]
    alerts, infos = calculate_alerts("x", df, thresholds, {"instance_id_keys": ["instance_id"]}, n=3)
    assert alerts == [] and infos == []


def test_calculate_alerts_invalid_threshold_method_raises():
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "90"], [2, "95"]]},
        ]
    )
    thresholds = [{"method": "~=", "value": 1, "level": "error"}]
    with pytest.raises(BaseAppException, match="Invalid threshold method"):
        calculate_alerts("x", df, thresholds, {"instance_id_keys": ["instance_id"]}, n=2)


def test_calculate_alerts_first_matching_threshold_wins():
    df = vm_to_dataframe(
        [
            {"metric": {"instance_id": "h1"}, "values": [[1, "95"], [2, "96"]]},
        ]
    )
    thresholds = [
        {"method": ">", "value": 90, "level": "error"},
        {"method": ">", "value": 80, "level": "warning"},
    ]
    alerts, _ = calculate_alerts("x", df, thresholds, {"instance_id_keys": ["instance_id"]}, n=2)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "error"
