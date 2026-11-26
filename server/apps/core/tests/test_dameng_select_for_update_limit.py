"""Dameng select_for_update: schema init may drop FOR UPDATE; other processes page by pk."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models.query import QuerySet
from django.db.models.sql.compiler import SQLCompiler
from django.db.utils import NotSupportedError

from apps.core.db_patches import dameng
from migrate_patch.patches import lock_compat

pytestmark = pytest.mark.django_db

_ORIGINAL_GETITEM = QuerySet.__getitem__
_ORIGINAL_EXISTS = QuerySet.exists


def _dameng_lock_features(monkeypatch):
    monkeypatch.setattr(connection.features, "has_select_for_update", True)
    monkeypatch.setattr(connection.features, "supports_select_for_update_with_limit", False)


def _reset_patches(compiler_original):
    SQLCompiler.as_sql = compiler_original
    QuerySet.__getitem__ = _ORIGINAL_GETITEM
    QuerySet.exists = _ORIGINAL_EXISTS
    lock_compat._SELECT_FOR_UPDATE_LIMIT_PATCHED = False
    lock_compat._SELECT_FOR_UPDATE_WINDOW_PATCHED = False


def test_dameng_patch_allows_sliced_select_for_update_when_limit_unsupported(monkeypatch):
    _dameng_lock_features(monkeypatch)
    original = SQLCompiler.as_sql
    _reset_patches(original)
    try:
        with pytest.raises(NotSupportedError, match="LIMIT/OFFSET is not supported with select_for_update"):
            list(ContentType.objects.select_for_update().order_by("pk")[:1])

        lock_compat.install_select_for_update_limit_compat()
        list(ContentType.objects.select_for_update().order_by("pk")[:1])
    finally:
        _reset_patches(original)


def test_server_process_pages_select_for_update_without_dropping_the_lock(monkeypatch):
    _dameng_lock_features(monkeypatch)
    monkeypatch.setattr(lock_compat.sys, "argv", ["celery", "-A", "config", "worker"])
    original = SQLCompiler.as_sql
    _reset_patches(original)
    compiled = []
    original_execute = SQLCompiler.execute_sql

    def execute_sql(self, *args, **kwargs):
        sql = self.as_sql()[0]
        compiled.append(sql)
        # SQLite accepts the feature flag but not the FOR UPDATE clause.
        if getattr(self.query, "select_for_update", False) and connection.vendor == "sqlite":
            self.query.select_for_update = False
            try:
                return original_execute(self, *args, **kwargs)
            finally:
                self.query.select_for_update = True
        return original_execute(self, *args, **kwargs)

    monkeypatch.setattr(SQLCompiler, "execute_sql", execute_sql)
    try:
        assert dameng._patch_select_for_update_with_limit() is None
        dameng._patch_select_for_update_window()
        from django.db import transaction

        with transaction.atomic():
            row = ContentType.objects.select_for_update().order_by("pk").first()
            page = list(ContentType.objects.select_for_update().order_by("pk")[:2])
            assert ContentType.objects.select_for_update().filter(pk=row.pk).exists() is True
        assert row is not None
        assert page and page[0].pk == row.pk
        limited = [sql for sql in compiled if "LIMIT" in sql.upper()]
        locked = [sql for sql in compiled if "FOR UPDATE" in sql.upper()]
        assert limited and all("FOR UPDATE" not in sql.upper() for sql in limited)
        assert locked and all("LIMIT" not in sql.upper() for sql in locked)
    finally:
        _reset_patches(original)

    assert SQLCompiler.as_sql is original


def test_batch_init_process_installs_select_for_update_limit_compat(monkeypatch):
    _dameng_lock_features(monkeypatch)
    monkeypatch.setattr(lock_compat.sys, "argv", ["manage.py", "batch_init", "--apps=node_mgmt"])
    original = SQLCompiler.as_sql
    _reset_patches(original)
    try:
        assert lock_compat.install_select_for_update_limit_compat_for_schema_init() is True
        list(ContentType.objects.select_for_update().order_by("pk")[:1])
    finally:
        _reset_patches(original)
