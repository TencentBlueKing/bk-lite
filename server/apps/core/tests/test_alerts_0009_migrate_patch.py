"""alerts.0009 信创补丁：FakeAddIndex 必须配对，删除必须能从任意中断点重跑。

0005 补丁用 FakeAddIndex 跳过 alerts_sess_event_i_5ab59a_idx，原始 0009 按名删除会失败；
达梦和 MySQL 系 DDL 自动提交，失败前的删除已经生效，重跑时对象已经不在。
"""

from __future__ import annotations

import importlib.util
import logging
from importlib import import_module
from pathlib import Path

import pytest
from django.db import DatabaseError, connection, migrations
from django.db.migrations.loader import MigrationLoader

SERVER_ROOT = Path(__file__).resolve().parents[3]
PATCH_ROOT = SERVER_ROOT / "migrate_patch" / "patches"
ENGINES = ("dameng", "mysql", "gaussdb", "goldendb", "oceanbase")
FK_INDEX = "alerts_sess_event_i_5ab59a_idx"
SESSION_INDEX = "alerts_sess_session_76b0b9_idx"
PATCH_0005 = "0005_sessioneventrelation_aggregationrules_image_and_more.py"
MIGRATION_0009 = "0009_remove_correlationrules_aggregation_rules_and_more"
PATCH_0009 = f"{MIGRATION_0009}.py"
PREVIOUS = ("alerts", "0008_alarmstrategy_and_more")
LEGACY_MODELS = ("AggregationRules", "CorrelationRules", "SessionWindow", "SessionEventRelation")


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"{path.parent.parent.name}_{path.stem}", path)
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

    operations = _operations(path)
    rows = _index_ops(operations)
    assert [row for row in rows if row[1] == FK_INDEX] == [("FakeRemoveIndex", FK_INDEX, "remove")]
    assert [row for row in rows if row[1] == SESSION_INDEX] == [("RemoveIndexIfExists", SESSION_INDEX, "remove")]

    original = import_module(f"apps.alerts.migrations.{MIGRATION_0009}").Migration.operations
    assert [op.describe() for op in operations] == [op.describe() for op in original]
    assert all(type(op).__name__ == "FakeRemoveIndex" or type(op).__name__.endswith("IfExists") for op in operations)


def _legacy_state():
    return MigrationLoader(connection, ignore_no_migrations=True).project_state(PREVIOUS)


def _legacy_tables(state) -> set[str]:
    tables = set()
    for name in LEGACY_MODELS:
        model = state.apps.get_model("alerts", name)
        tables.add(model._meta.db_table)
        for field in model._meta.local_many_to_many:
            if field.remote_field.through._meta.auto_created:
                tables.add(field.remote_field.through._meta.db_table)
    return tables


def _existing(tables: set[str]) -> set[str]:
    return tables & set(connection.introspection.table_names())


def _drop_remaining_legacy_tables(state):
    # delete_model(CorrelationRules) 会连带删自动中间表；中间表可能已不在，所以逐表判断。
    through = state.apps.get_model("alerts", "CorrelationRules")._meta.get_field("aggregation_rules").remote_field.through
    without_m2m = state.clone()
    migrations.RemoveField(model_name="correlationrules", name="aggregation_rules").state_forwards("alerts", without_m2m)
    models = [through, *(without_m2m.apps.get_model("alerts", name) for name in reversed(LEGACY_MODELS))]
    existing = set(connection.introspection.table_names())
    with connection.schema_editor() as editor:
        for model in models:
            if model._meta.db_table in existing:
                editor.delete_model(model)


@pytest.fixture
def legacy_alerts_tables():
    """在测试库上按 0008 的模型建出 0009 要删的旧表，用完全部清掉。"""
    state = _legacy_state()
    tables = _legacy_tables(state)
    assert not _existing(tables)
    with connection.schema_editor() as editor:
        for name in LEGACY_MODELS:
            editor.create_model(state.apps.get_model("alerts", name))
    try:
        yield state, tables
    finally:
        _drop_remaining_legacy_tables(state)


def _apply(migration, state):
    with connection.schema_editor() as editor:
        migration.apply(state.clone(), editor)


def _patched_0009(engine: str):
    return _load_module(PATCH_ROOT / engine / "alerts" / PATCH_0009).Migration(MIGRATION_0009, "alerts")


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_patched_0009_drops_legacy_tables_and_can_run_again(engine, legacy_alerts_tables):
    state, tables = legacy_alerts_tables

    _apply(_patched_0009(engine), state)
    assert not _existing(tables)

    _apply(_patched_0009(engine), state)
    assert not _existing(tables)


@pytest.mark.integration
@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("engine", ENGINES)
def test_patched_0009_resumes_after_original_0009_stopped_midway(engine, legacy_alerts_tables):
    state, tables = legacy_alerts_tables
    original = import_module(f"apps.alerts.migrations.{MIGRATION_0009}").Migration(MIGRATION_0009, "alerts")
    # 达梦和 MySQL 系上，原始 0009 在第 3 步 DROP INDEX 失败前，已经提交了前两步。
    stopped = migrations.Migration("0009_stopped_before_drop_index", "alerts")
    stopped.operations = original.operations[:2]
    _apply(stopped, state)

    with pytest.raises(DatabaseError):
        _apply(original, state)

    _apply(_patched_0009(engine), state)
    assert not _existing(tables)


def test_dameng_schema_editor_skips_only_duplicate_plain_index(monkeypatch, caplog):
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

    from migrate_patch.patches.compat_ops import install_idempotent_schema_editor

    class DuplicateIndex(Exception):
        pass

    def original(self, sql, params=()):
        raise DuplicateIndex("[CODE:-3236]此列列表已索引")

    features_class = type(connection.features)
    monkeypatch.setattr(BaseDatabaseSchemaEditor, "execute", original)
    monkeypatch.setattr(features_class, "can_rollback_ddl", features_class.can_rollback_ddl)

    execute = install_idempotent_schema_editor()

    assert features_class.can_rollback_ddl is True
    with caplog.at_level(logging.WARNING, logger="app"):
        assert execute(None, 'CREATE INDEX "alerts_dup_idx" ON "alerts_t" ("c")') is None
    record = next(r for r in caplog.records if r.msg.startswith("event=dameng_duplicate_index_skipped"))
    assert record.args == ("alerts_dup_idx", "DuplicateIndex")
    assert record.getMessage() == "event=dameng_duplicate_index_skipped index=alerts_dup_idx failed_stage=migrate error_type=DuplicateIndex"

    with pytest.raises(DuplicateIndex):
        execute(None, 'CREATE UNIQUE INDEX "alerts_uniq" ON "alerts_t" ("c")')
    with pytest.raises(DuplicateIndex):
        execute(None, 'ALTER TABLE "alerts_t" ADD CONSTRAINT "alerts_uniq" UNIQUE ("c")')


def test_dameng_schema_editor_reraises_unrelated_errors(monkeypatch):
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor

    from migrate_patch.patches.compat_ops import install_idempotent_schema_editor

    def original(self, sql, params=()):
        raise RuntimeError("disk full")

    features_class = type(connection.features)
    monkeypatch.setattr(BaseDatabaseSchemaEditor, "execute", original)
    monkeypatch.setattr(features_class, "can_rollback_ddl", features_class.can_rollback_ddl)

    execute = install_idempotent_schema_editor()

    with pytest.raises(RuntimeError, match="disk full"):
        execute(None, 'CREATE INDEX "alerts_dup_idx" ON "alerts_t" ("c")')
