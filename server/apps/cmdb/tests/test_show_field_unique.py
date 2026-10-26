"""同一用户、同一模型的展示列必须只有一行。"""

import json
import threading
from datetime import timedelta

import pytest
from django.core.exceptions import MultipleObjectsReturned
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from apps.cmdb.models.show_field import ShowField
from apps.cmdb.services.instance import InstanceManage
from apps.core.exceptions.base_app_exception import BaseAppException

OLD_TARGET = [("cmdb", "0060_subscription_attribute_lifecycle")]
NEW_TARGET = [("cmdb", "0061_showfield_created_by_model_unique")]
BACKUP_TABLE = "cmdb_showfield_duplicate_backup"
CONSTRAINT_NAME = "uniq_showfield_created_by_model"


def _cmdb_leaf_nodes():
    executor = MigrationExecutor(connection)
    return [node for node in executor.loader.graph.leaf_nodes() if node[0] == "cmdb"]


def _clear_backup_table():
    if not _table_exists(BACKUP_TABLE):
        return
    with connection.cursor() as cursor:
        cursor.execute(f"TRUNCATE TABLE {BACKUP_TABLE}")


def _table_exists(table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = %s
            """,
            [table_name],
        )
        return cursor.fetchone() is not None


def _backup_rows():
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT original_id, created_by, model_id, show_fields, created_at, updated_at
            FROM {BACKUP_TABLE}
            ORDER BY original_id
            """
        )
        rows = cursor.fetchall()
    normalized = []
    for original_id, created_by, model_id, show_fields, created_at, updated_at in rows:
        if isinstance(show_fields, str):
            show_fields = json.loads(show_fields)
        normalized.append((original_id, created_by, model_id, show_fields, created_at, updated_at))
    return normalized


def _constraint_columns(table_name):
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, table_name)
    constraint = constraints.get(CONSTRAINT_NAME)
    if constraint is None:
        return None
    return list(constraint["columns"])


@pytest.mark.django_db(transaction=True)
def test_migration_dedupes_show_field_and_reverse_restores_backup():
    latest = _cmdb_leaf_nodes()
    _clear_backup_table()
    executor = MigrationExecutor(connection)
    executor.migrate(OLD_TARGET)
    try:
        old_apps = executor.loader.project_state(OLD_TARGET).apps
        historical = old_apps.get_model("cmdb", "ShowField")
        moment = timezone.now().replace(microsecond=0)
        older = historical.objects.create(created_by="alice", model_id="host", show_fields=["stale"])
        newer = historical.objects.create(created_by="alice", model_id="host", show_fields=["fresh"])
        low = historical.objects.create(created_by="bob", model_id="host", show_fields=["low"])
        high = historical.objects.create(created_by="bob", model_id="host", show_fields=["high"])
        solo = historical.objects.create(created_by="alice", model_id="net", show_fields=["solo"])
        historical.objects.filter(pk=older.pk).update(created_at=moment, updated_at=moment)
        historical.objects.filter(pk=newer.pk).update(
            created_at=moment + timedelta(seconds=1),
            updated_at=moment + timedelta(seconds=10),
        )
        historical.objects.filter(pk__in=[low.pk, high.pk]).update(
            created_at=moment + timedelta(seconds=2),
            updated_at=moment + timedelta(seconds=2),
        )
        historical.objects.filter(pk=solo.pk).update(
            created_at=moment + timedelta(seconds=3),
            updated_at=moment + timedelta(seconds=3),
        )
        removed = []
        for row in historical.objects.filter(pk__in=[older.pk, low.pk]):
            row.refresh_from_db()
            removed.append(row)
        assert low.pk < high.pk

        with pytest.raises(MultipleObjectsReturned):
            InstanceManage.create_or_update(
                {"show_fields": ["later"], "model_id": "host", "created_by": "alice"}
            )

        executor = MigrationExecutor(connection)
        executor.migrate(NEW_TARGET)
        migrated = executor.loader.project_state(NEW_TARGET).apps.get_model("cmdb", "ShowField")

        assert list(migrated.objects.filter(created_by="alice", model_id="host").values_list("id", "show_fields")) == [
            (newer.pk, ["fresh"])
        ]
        assert list(migrated.objects.filter(created_by="bob", model_id="host").values_list("id", "show_fields")) == [
            (high.pk, ["high"])
        ]
        assert migrated.objects.get(pk=solo.pk).show_fields == ["solo"]
        assert _constraint_columns(migrated._meta.db_table) == ["created_by", "model_id"]
        assert sorted(_backup_rows()) == sorted(
            [
                (row.pk, row.created_by, row.model_id, row.show_fields, row.created_at, row.updated_at)
                for row in removed
            ]
        )

        saved = InstanceManage.create_or_update(
            {"show_fields": ["saved"], "model_id": "host", "created_by": "alice"}
        )
        assert saved["show_fields"] == ["saved"]
        assert migrated.objects.filter(created_by="alice", model_id="host").count() == 1
        with pytest.raises(BaseAppException, match="展示字段不能为空！"):
            InstanceManage.create_or_update(
                {"show_fields": [], "model_id": "host", "created_by": "alice"}
            )

        executor = MigrationExecutor(connection)
        executor.migrate(OLD_TARGET)
        restored = executor.loader.project_state(OLD_TARGET).apps.get_model("cmdb", "ShowField")
        assert _constraint_columns(restored._meta.db_table) is None
        assert _table_exists(BACKUP_TABLE) is False
        restored_older = restored.objects.get(pk=older.pk)
        restored_low = restored.objects.get(pk=low.pk)
        by_id = {row.pk: row for row in removed}
        assert (restored_older.created_at, restored_older.updated_at, restored_older.show_fields) == (
            by_id[older.pk].created_at,
            by_id[older.pk].updated_at,
            ["stale"],
        )
        assert (restored_low.created_at, restored_low.updated_at, restored_low.show_fields) == (
            by_id[low.pk].created_at,
            by_id[low.pk].updated_at,
            ["low"],
        )
        assert restored.objects.filter(pk=newer.pk).exists()
        assert restored.objects.filter(pk=high.pk).exists()
        with pytest.raises(MultipleObjectsReturned):
            InstanceManage.create_or_update(
                {"show_fields": ["again"], "model_id": "host", "created_by": "bob"}
            )
    finally:
        MigrationExecutor(connection).migrate(latest)
        _clear_backup_table()


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_save_keeps_one_submitted_row():
    barrier = threading.Barrier(2)
    original_save = ShowField.save
    errors = []

    def gated_save(self, *args, **kwargs):
        if kwargs.get("force_insert"):
            barrier.wait(timeout=10)
        return original_save(self, *args, **kwargs)

    def worker(show_fields):
        close_old_connections()
        try:
            InstanceManage.create_or_update(
                {"show_fields": show_fields, "model_id": "host", "created_by": "race-user"}
            )
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [
        threading.Thread(target=worker, args=(["left"],)),
        threading.Thread(target=worker, args=(["right"],)),
    ]
    ShowField.save = gated_save
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
    finally:
        ShowField.save = original_save

    assert [thread.is_alive() for thread in threads] == [False, False]
    assert errors == []
    rows = list(ShowField.objects.filter(created_by="race-user", model_id="host"))
    assert len(rows) == 1
    assert rows[0].show_fields in (["left"], ["right"])

    again = InstanceManage.create_or_update(
        {"show_fields": ["after"], "model_id": "host", "created_by": "race-user"}
    )
    assert again["show_fields"] == ["after"]
    assert ShowField.objects.filter(created_by="race-user", model_id="host").count() == 1
    assert InstanceManage.get_info("host", "race-user") == {"model_id": "host", "show_fields": ["after"]}


@pytest.mark.django_db
def test_sequential_save_and_empty_list_stay_unchanged():
    created = InstanceManage.create_or_update(
        {"show_fields": ["inst_name"], "model_id": "host", "created_by": "seq-user"}
    )
    updated = InstanceManage.create_or_update(
        {"show_fields": ["ip"], "model_id": "host", "created_by": "seq-user"}
    )
    assert created["model_id"] == "host"
    assert updated["show_fields"] == ["ip"]
    assert list(
        ShowField.objects.filter(created_by="seq-user", model_id="host").values_list("show_fields", flat=True)
    ) == [["ip"]]
    assert InstanceManage.get_info("host", "seq-user") == {"model_id": "host", "show_fields": ["ip"]}

    InstanceManage.create_or_update(
        {"show_fields": ["name"], "model_id": "net", "created_by": "seq-user"}
    )
    assert ShowField.objects.filter(created_by="seq-user").count() == 2

    with pytest.raises(BaseAppException, match="展示字段不能为空！"):
        InstanceManage.create_or_update(
            {"show_fields": [], "model_id": "host", "created_by": "seq-user"}
        )
    assert ShowField.objects.get(created_by="seq-user", model_id="host").show_fields == ["ip"]
