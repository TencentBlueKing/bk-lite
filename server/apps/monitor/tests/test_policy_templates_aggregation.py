import json
from pathlib import Path

from apps.monitor.services.policy_bulk import normalize_template_algorithms


VALID_GROUP_ALGORITHMS = {"avg", "max", "min", "sum", "count"}
VALID_WINDOW_ALGORITHMS = {
    "avg_over_time",
    "max_over_time",
    "min_over_time",
    "sum_over_time",
    "count_over_time",
    "last_over_time",
}


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
