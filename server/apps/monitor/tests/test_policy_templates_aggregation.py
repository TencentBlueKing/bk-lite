import json
from pathlib import Path

from apps.monitor.services.policy_bulk import (
    build_bulk_policy_payloads,
    normalize_template_algorithms,
)
from apps.monitor.tasks.utils.policy_methods import (
    GROUP_AGGREGATION_ALGORITHMS,
    WINDOW_AGGREGATION_ALGORITHMS,
)


VALID_GROUP_ALGORITHMS = GROUP_AGGREGATION_ALGORITHMS
VALID_WINDOW_ALGORITHMS = WINDOW_AGGREGATION_ALGORITHMS


def _iter_policy_items(value, path):
    if isinstance(value, dict):
        if "algorithm" in value:
            yield path, value
        for key, item in value.items():
            yield from _iter_policy_items(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_policy_items(item, f"{path}[{index}]")


def test_policy_templates_normalize_to_two_stage_aggregation_methods():
    root = Path(__file__).resolve().parents[1] / "support-files" / "plugins"
    errors = []

    for policy_path in root.rglob("policy.json"):
        data = json.loads(policy_path.read_text())
        for item_path, item in _iter_policy_items(data, str(policy_path)):
            group_algorithm, algorithm = normalize_template_algorithms(item)
            if group_algorithm not in VALID_GROUP_ALGORITHMS:
                errors.append(f"{item_path}: invalid normalized group_algorithm={group_algorithm!r}")
            if algorithm not in VALID_WINDOW_ALGORITHMS:
                errors.append(f"{item_path}: invalid normalized algorithm={algorithm!r}")

    assert errors == []


def test_normalize_keeps_rate_without_group_algorithm():
    group_algorithm, algorithm = normalize_template_algorithms({"algorithm": "rate"})
    assert group_algorithm == "avg"
    assert algorithm == "rate"


def test_normalize_keeps_count_if_and_changes_without_group_algorithm():
    assert normalize_template_algorithms({"algorithm": "count_if_over_time"}) == (
        "avg",
        "count_if_over_time",
    )
    assert normalize_template_algorithms({"algorithm": "changes"}) == ("avg", "changes")
    assert normalize_template_algorithms({"algorithm": "deriv"}) == ("avg", "deriv")


def test_bulk_payload_keeps_new_fields_from_template():
    payloads = build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "P95 比 1h 前高 50%",
                "metric_id": 101,
                "algorithm": "p95_over_time",
                "group_algorithm": "avg",
                "compare_mode": "offset_1h",
                "compare_value_kind": "percent",
                "count_predicate": {"method": ">", "value": 80},
                "forecast_target": 90,
                "forecast_lookback": {"type": "hour", "value": 4},
                "recovery_threshold": {"method": "<", "value": 70},
                "threshold": [{"level": "warning", "method": ">", "value": 50}],
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={},
    )
    payload = payloads[0]
    assert payload["algorithm"] == "p95_over_time"
    assert payload["group_algorithm"] == "avg"
    assert payload["compare_mode"] == "offset_1h"
    assert payload["compare_value_kind"] == "percent"
    assert payload["count_predicate"] == {"method": ">", "value": 80}
    assert payload["forecast_target"] == 90
    assert payload["forecast_target_unit"] == ""
    assert payload["forecast_lookback"] == {"type": "hour", "value": 4}
    assert payload["recovery_threshold"] == {"method": "<", "value": 70}
