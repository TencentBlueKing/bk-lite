import importlib.util
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
LEAF_0064 = {
    ("monitor", "0064_monitorevent_lifecycle_action"),
    ("monitor", "0064_monitorinstance_k8s_daemonset_tolerations"),
}


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(
        f"monitor_{filename}_test_module",
        MIGRATIONS_DIR / filename,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_0064_branches_share_the_same_parent():
    lifecycle = _load_migration("0064_monitorevent_lifecycle_action.py")
    tolerations = _load_migration("0064_monitorinstance_k8s_daemonset_tolerations.py")

    assert lifecycle.Migration.dependencies == [
        ("monitor", "0063_remove_policy_template_scope_name_unique")
    ]
    assert tolerations.Migration.dependencies == [
        ("monitor", "0063_remove_policy_template_scope_name_unique")
    ]


def test_0065_merges_both_0064_leaves_without_schema_ops():
    merge = _load_migration("0065_merge_lifecycle_action_and_k8s_tolerations.py")

    assert set(merge.Migration.dependencies) == LEAF_0064
    assert merge.Migration.operations == []
