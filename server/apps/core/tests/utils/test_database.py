from contextlib import nullcontext
from importlib import import_module
from types import SimpleNamespace

import pytest
from django.db import migrations

from apps.core.utils import database


class _Manager:
    db = "default"

    def __init__(self):
        self.bulk_calls = []

    def bulk_create(self, objects, *, batch_size=None):
        self.bulk_calls.append((objects, batch_size))
        return objects


class _Object:
    def __init__(self):
        self.save_calls = []

    def save(self, **kwargs):
        self.save_calls.append(kwargs)


def test_bulk_create_with_primary_keys_uses_bulk_insert_when_backend_returns_ids(monkeypatch):
    manager = _Manager()
    objects = [_Object(), _Object()]
    monkeypatch.setattr(
        database,
        "connections",
        {"default": SimpleNamespace(features=SimpleNamespace(can_return_rows_from_bulk_insert=True))},
    )

    result = database.bulk_create_with_primary_keys(manager, objects, batch_size=20)

    assert result == objects
    assert manager.bulk_calls == [(objects, 20)]
    assert all(not obj.save_calls for obj in objects)


def test_bulk_create_with_primary_keys_inserts_individually_when_backend_cannot_return_ids(monkeypatch):
    manager = _Manager()
    objects = [_Object(), _Object()]
    monkeypatch.setattr(
        database,
        "connections",
        {"default": SimpleNamespace(features=SimpleNamespace(can_return_rows_from_bulk_insert=False))},
    )
    atomic_calls = []
    monkeypatch.setattr(
        database.transaction,
        "atomic",
        lambda *, using: atomic_calls.append(using) or nullcontext(),
    )

    result = database.bulk_create_with_primary_keys(manager, objects)

    assert result == objects
    assert manager.bulk_calls == []
    assert atomic_calls == ["default"]
    assert [obj.save_calls for obj in objects] == [
        [{"force_insert": True, "using": "default"}],
        [{"force_insert": True, "using": "default"}],
    ]


@pytest.mark.parametrize(
    ("module_name", "preflight_name"),
    [
        (
            "apps.operation_analysis.migrations.0022_cross_database_active_share_guard",
            "ensure_active_links_unique",
        ),
        (
            "apps.operation_analysis.migrations.0023_cross_database_execution_guards",
            "ensure_execution_keys_unique",
        ),
        ("apps.patch_mgmt.migrations.0008_cross_database_kb_guard", "ensure_kb_numbers_unique"),
        ("apps.system_mgmt.migrations.0045_cross_database_running_guards", "ensure_running_runs_unique"),
    ],
)
def test_mysql_guard_migrations_preflight_before_nontransactional_ddl(module_name, preflight_name):
    operations = import_module(module_name).Migration.operations

    assert isinstance(operations[0], migrations.RunPython)
    assert operations[0].code.__name__ == preflight_name
    first_add_field = next(index for index, operation in enumerate(operations) if isinstance(operation, migrations.AddField))
    assert first_add_field > 0
