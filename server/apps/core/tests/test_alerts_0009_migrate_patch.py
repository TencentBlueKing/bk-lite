"""alerts.0009 信创补丁：FakeAddIndex 必须配对可重入删除。

达梦空库在 0005 用 FakeAddIndex 跳过 alerts_sess_event_i_5ab59a_idx，
0009 若按原名 DROP INDEX 会得到 -2139；DDL 已提交则重跑再报缺表 -2106。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from django.db import migrations

SERVER_ROOT = Path(__file__).resolve().parents[3]
PATCH_ROOT = SERVER_ROOT / "migrate_patch" / "patches"
ENGINES = ("dameng", "mysql", "gaussdb", "goldendb", "oceanbase")
FK_INDEX = "alerts_sess_event_i_5ab59a_idx"
SESSION_INDEX = "alerts_sess_session_76b0b9_idx"
PATCH_0005 = "0005_sessioneventrelation_aggregationrules_image_and_more.py"
PATCH_0009 = "0009_remove_correlationrules_aggregation_rules_and_more.py"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _operations(path: Path):
    return list(_load_module(path).Migration.operations)


def _index_ops(operations):
    rows = []
    for op in operations:
        if isinstance(op, migrations.RemoveIndex):
            rows.append((type(op).__name__, op.name, "remove"))
        elif isinstance(op, migrations.AddIndex):
            rows.append((type(op).__name__, op.index.name, "add"))
    return rows


def _engine_0005_faked_fk_index(engine: str) -> bool:
    path = PATCH_ROOT / engine / "alerts" / PATCH_0005
    if not path.exists():
        return False
    return any(kind == "add" and name == FK_INDEX and type_name.startswith("Fake") for type_name, name, kind in _index_ops(_operations(path)))


@pytest.mark.parametrize("engine", ENGINES)
def test_engine_that_skips_fk_index_in_0005_patches_0009(engine):
    if not _engine_0005_faked_fk_index(engine):
        pytest.skip(f"{engine} 0005 未 FakeAddIndex {FK_INDEX}")

    path = PATCH_ROOT / engine / "alerts" / PATCH_0009
    assert path.exists(), f"{engine} 缺少 alerts/0009 补丁，空库会在 DROP INDEX {FK_INDEX} 失败"

    rows = _index_ops(_operations(path))
    fk_ops = [row for row in rows if row[1] == FK_INDEX]
    assert fk_ops, f"{engine} 0009 补丁未声明 {FK_INDEX}"
    assert all(type_name == "FakeRemoveIndex" and kind == "remove" for type_name, _, kind in fk_ops), fk_ops

    session_ops = [row for row in rows if row[1] == SESSION_INDEX]
    assert session_ops, f"{engine} 0009 补丁未处理 {SESSION_INDEX}"
    assert all(not type_name.startswith("Fake") and kind == "remove" for type_name, _, kind in session_ops), session_ops


def test_missing_object_error_accepts_dameng_codes():
    from django.db.utils import ProgrammingError

    from migrate_patch.patches.compat_ops import missing_object_error

    class _Arg:
        def __init__(self, code):
            self.code = code

    class _Driver(Exception):
        pass

    table_missing = _Driver(_Arg(-2106), "invalid table or view name")
    index_missing = _Driver(_Arg(-2139), "Index not exists")
    other = _Driver(_Arg(-3236), "此列列表已索引")
    wrapped = ProgrammingError("Index not exists")
    wrapped.__cause__ = index_missing

    assert missing_object_error(table_missing) is True
    assert missing_object_error(index_missing) is True
    assert missing_object_error(wrapped) is True
    assert missing_object_error(other) is False


def test_run_ignoring_missing_object_swallows_dameng_table_missing():
    from migrate_patch.patches.compat_ops import run_ignoring_missing_object

    class _Arg:
        def __init__(self, code):
            self.code = code

    class _Driver(Exception):
        pass

    def boom():
        raise _Driver(_Arg(-2106), "invalid table or view name")

    assert run_ignoring_missing_object(boom) is None


def test_run_ignoring_missing_object_reraises_unrelated_errors():
    from migrate_patch.patches.compat_ops import run_ignoring_missing_object

    def boom():
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError, match="disk full"):
        run_ignoring_missing_object(boom)


def test_already_indexed_error_accepts_dameng_duplicate_index():
    from migrate_patch.patches.compat_ops import already_indexed_error

    class _Arg:
        def __init__(self, code):
            self.code = code

    class _Driver(Exception):
        pass

    assert already_indexed_error(_Driver(_Arg(-3236), "such column list already indexed")) is True
    assert already_indexed_error(_Driver(_Arg(-2139), "Index not exists")) is False


def test_dameng_0009_makes_already_applied_drops_idempotent():
    ops = _operations(PATCH_ROOT / "dameng" / "alerts" / PATCH_0009)
    assert type(ops[0]).__name__ == "RemoveFieldIfExists"
    assert ops[0].name == "aggregation_rules"
    assert type(ops[1]).__name__ == "AlterUniqueTogetherIfExists"
