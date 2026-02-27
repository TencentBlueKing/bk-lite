import importlib.util
from pathlib import Path

import pandas as pd


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_format_dimension_value_with_display_name_and_empty_value():
    dimension_module = _load_module(
        "dimension_module",
        Path(__file__).resolve().parents[1] / "utils" / "dimension.py",
    )

    dimensions = {"instance_id": "i-1", "agent_id": ""}
    ordered_keys = ["instance_id", "agent_id"]
    name_map = {"instance_id": "实例ID", "agent_id": "节点"}

    result = dimension_module.format_dimension_value(
        dimensions,
        ordered_keys=ordered_keys,
        name_map=name_map,
    )

    assert result == "实例ID:i-1,节点:"


def test_calculate_alerts_should_render_resource_and_dimension_value():
    calculate_module = _load_module(
        "policy_calculate_module",
        Path(__file__).resolve().parents[1] / "tasks" / "utils" / "policy_calculate.py",
    )

    df = pd.DataFrame(
        [
            {
                "instance_id": ("i-1", "a-1"),
                "values": [[1700000000, "92"]],
            }
        ]
    )

    thresholds = [{"method": ">", "value": 80, "level": "warning"}]
    template_context = {
        "monitor_object": "主机",
        "metric_name": "CPU使用率",
        "instances_map": {"('i-1',)": "主机A"},
        "instance_id_keys": ["instance_id", "agent_id"],
        "dimension_name_map": {"instance_id": "实例ID", "agent_id": "节点"},
        "display_unit": "%",
        "enum_value_map": {},
    }

    alert_events, info_events = calculate_module.calculate_alerts(
        "${resource_name}|${dimension_value}|${instance_name}|${value}",
        df,
        thresholds,
        template_context,
    )

    assert len(alert_events) == 1
    assert len(info_events) == 0
    assert alert_events[0]["content"] == "主机A|节点:a-1|主机A - agent_id:a-1|92.00%"
