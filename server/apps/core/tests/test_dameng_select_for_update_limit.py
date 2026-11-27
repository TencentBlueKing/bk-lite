"""Dameng SQLCompiler patch: schema init may drop FOR UPDATE; a server process must not."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.models.sql.compiler import SQLCompiler
from django.db.utils import NotSupportedError

from apps.core.db_patches import dameng
from migrate_patch.patches import lock_compat

pytestmark = pytest.mark.django_db


def _reset_compiler(original):
    SQLCompiler.as_sql = original
    lock_compat._SELECT_FOR_UPDATE_LIMIT_PATCHED = False


def test_dameng_patch_allows_sliced_select_for_update_when_limit_unsupported(monkeypatch):
    monkeypatch.setattr(connection.features, "supports_select_for_update_with_limit", False)
    original = SQLCompiler.as_sql
    lock_compat._SELECT_FOR_UPDATE_LIMIT_PATCHED = False
    try:
        with pytest.raises(NotSupportedError, match="LIMIT/OFFSET is not supported with select_for_update"):
            list(ContentType.objects.select_for_update().order_by("pk")[:1])

        lock_compat.install_select_for_update_limit_compat()
        list(ContentType.objects.select_for_update().order_by("pk")[:1])
    finally:
        _reset_compiler(original)


def test_server_process_keeps_select_for_update_limit_error(monkeypatch):
    monkeypatch.setattr(connection.features, "supports_select_for_update_with_limit", False)
    monkeypatch.setattr(lock_compat.sys, "argv", ["uvicorn", "asgi:application"])
    original = SQLCompiler.as_sql
    lock_compat._SELECT_FOR_UPDATE_LIMIT_PATCHED = False
    try:
        assert dameng._patch_select_for_update_with_limit() is None
        assert lock_compat.install_select_for_update_limit_compat_for_schema_init() is False
        with pytest.raises(NotSupportedError, match="LIMIT/OFFSET is not supported with select_for_update"):
            ContentType.objects.select_for_update().order_by("pk").first()
    finally:
        _reset_compiler(original)


def test_batch_init_process_installs_select_for_update_limit_compat(monkeypatch):
    monkeypatch.setattr(connection.features, "supports_select_for_update_with_limit", False)
    monkeypatch.setattr(lock_compat.sys, "argv", ["manage.py", "batch_init", "--apps=node_mgmt"])
    original = SQLCompiler.as_sql
    lock_compat._SELECT_FOR_UPDATE_LIMIT_PATCHED = False
    try:
        assert lock_compat.install_select_for_update_limit_compat_for_schema_init() is True
        list(ContentType.objects.select_for_update().order_by("pk")[:1])
    finally:
        _reset_compiler(original)
