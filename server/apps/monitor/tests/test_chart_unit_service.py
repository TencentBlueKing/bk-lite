from copy import deepcopy

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.services.chart_unit import (
    convert_snapshots_copy,
    convert_vm_result_copy,
    resolve_chart_unit,
)


def test_resolve_chart_unit_prefers_threshold_and_supports_legacy_fallback():
    assert resolve_chart_unit("bytes", "bytes", "kibibytes") == "kibibytes"
    assert resolve_chart_unit("bytes", "kibibytes", "") == "kibibytes"
    assert resolve_chart_unit("bytes", "", "") == "bytes"
    assert resolve_chart_unit("", "", "") == ""


def test_convert_vm_result_copy_converts_values_without_mutating_input():
    data = {
        "status": "success",
        "data": {
            "result": [
                {
                    "metric": {"instance_id": "host-1"},
                    "values": [[1, "2048"], [2, None], [3, "1024"]],
                }
            ]
        },
    }
    original = deepcopy(data)

    converted = convert_vm_result_copy(data, "bytes", "kibibytes")

    assert converted["data"]["result"][0]["values"] == [
        [1, "2.0"],
        [2, None],
        [3, "1.0"],
    ]
    assert data == original


def test_convert_snapshots_copy_converts_values_without_mutating_input():
    snapshots = [
        {
            "event_id": "event-1",
            "raw_data": {
                "metric": {"mount": "/data"},
                "values": [[1, "2048"], [2, None]],
            },
        },
        {"event_id": "event-2", "raw_data": None},
        {"event_id": "event-3"},
    ]
    original = deepcopy(snapshots)

    converted = convert_snapshots_copy(snapshots, "bytes", "kibibytes")

    assert converted[0]["raw_data"]["values"] == [[1, "2.0"], [2, None]]
    assert converted[1]["raw_data"] is None
    assert "raw_data" not in converted[2]
    assert snapshots == original


def test_conversion_returns_an_independent_copy_when_units_are_equal():
    data = {"data": {"result": [{"values": [[1, "1"]]}]}}

    converted = convert_vm_result_copy(data, "bytes", "bytes")

    assert converted == data
    assert converted is not data
    assert converted["data"]["result"][0] is not data["data"]["result"][0]


@pytest.mark.parametrize(
    "convert, payload",
    [
        (convert_vm_result_copy, {"data": {"result": []}}),
        (convert_snapshots_copy, []),
    ],
)
def test_conversion_rejects_units_from_different_systems(convert, payload):
    with pytest.raises(BaseAppException, match="chart unit is not convertible"):
        convert(payload, "bytes", "percent")
