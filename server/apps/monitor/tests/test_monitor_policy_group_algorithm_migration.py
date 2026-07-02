import importlib.util
import types
from pathlib import Path


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "monitor_policy_group_algorithm_migration_test_module",
        Path(__file__).resolve().parents[1] / "migrations" / "0042_monitorpolicy_group_algorithm.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _PolicyList(list):
    def only(self, *fields):
        return self

    def bulk_update(self, policies, fields):
        self.updated = list(policies)
        self.updated_fields = list(fields)


def test_group_algorithm_migration_maps_legacy_algorithms():
    module = _load_migration_module()
    policies = _PolicyList(
        [
            types.SimpleNamespace(algorithm="AVG", group_algorithm=""),
            types.SimpleNamespace(algorithm="max_over_time", group_algorithm=""),
            types.SimpleNamespace(algorithm="COUNT", group_algorithm=""),
            types.SimpleNamespace(algorithm="LAST_OVER_TIME", group_algorithm=""),
        ]
    )

    class MonitorPolicy:
        objects = policies

    apps = types.SimpleNamespace(get_model=lambda app_label, model_name: MonitorPolicy)

    module.migrate_policy_algorithms(apps, None)

    assert [(item.group_algorithm, item.algorithm) for item in policies] == [
        ("avg", "avg_over_time"),
        ("max", "max_over_time"),
        ("count", "last_over_time"),
        ("avg", "last_over_time"),
    ]
    assert policies.updated == list(policies)
    assert policies.updated_fields == ["group_algorithm", "algorithm"]
