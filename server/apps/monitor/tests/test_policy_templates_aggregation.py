import json
from pathlib import Path

from apps.monitor.services.policy_bulk import normalize_template_algorithms
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
