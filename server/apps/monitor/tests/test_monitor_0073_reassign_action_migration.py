import importlib.util
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def _load_migration(filename: str):
    spec = importlib.util.spec_from_file_location(
        f"monitor_{filename}_test_module",
        MIGRATIONS_DIR / filename,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_0072_source_template_stays_on_0071():
    source_template = _load_migration("0072_monitorpolicy_source_template.py")

    assert source_template.Migration.dependencies == [
        ("monitor", "0071_collectconfig_applied_fingerprints")
    ]


def test_0073_reassign_action_follows_source_template():
    reassign = _load_migration("0073_monitorevent_reassign_action.py")

    assert reassign.Migration.dependencies == [
        ("monitor", "0072_monitorpolicy_source_template")
    ]
    assert any(
        getattr(operation, "name", None) == "action" for operation in reassign.Migration.operations
    )
