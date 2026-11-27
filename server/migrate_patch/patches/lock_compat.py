"""Portable row-lock helpers for migrate_patch on frozen images.

``apps.core.utils.queryset_lock`` is the product API. Frozen WeOps X images
do not ship that module, so Dameng migrate_patch copies import this file
instead.
"""

import sys
from pathlib import Path

_SELECT_FOR_UPDATE_LIMIT_PATCHED = False
_SCHEMA_INIT_COMMANDS = frozenset({"migrate", "batch_init"})


def is_schema_init_process(argv: list[str] | None = None) -> bool:
    """True only for ``manage.py migrate`` and ``manage.py batch_init``.

    ``startup.sh`` runs those as their own processes. Uvicorn, gunicorn, and
    celery must not take the compiler workaround: it drops FOR UPDATE from
    every limited ``select_for_update()``, including ``.first()``.
    """
    args = sys.argv if argv is None else argv
    for arg in args[1:]:
        if arg.startswith("-"):
            continue
        if Path(arg).name in _SCHEMA_INIT_COMMANDS:
            return True
    return False


def install_select_for_update_limit_compat_for_schema_init() -> bool:
    """Install the compiler workaround only while migrating or batch-initializing."""
    if not is_schema_init_process():
        return False
    install_select_for_update_limit_compat()
    return True


def install_select_for_update_limit_compat():
    """Drop FOR UPDATE when Django would combine it with LIMIT/OFFSET.

    Dameng sets ``supports_select_for_update_with_limit = False``. Frozen
    ``exists()`` and ``queryset[:N]`` after ``select_for_update()`` otherwise
    raise ``NotSupportedError`` at compile time. Call this only from
    ``install_select_for_update_limit_compat_for_schema_init`` or a test.
    Migrations that can rebuild should still use ``list_locked_batch`` so the
    page is locked by primary key. A long-lived process must not install this:
    ``QuerySet.first()`` is ``[:1]``, and dropping FOR UPDATE there removes the
    row lock from queue claims and other read-modify-write paths.
    """
    global _SELECT_FOR_UPDATE_LIMIT_PATCHED
    if _SELECT_FOR_UPDATE_LIMIT_PATCHED:
        return

    from django.db.models.sql.compiler import SQLCompiler

    original_as_sql = SQLCompiler.as_sql

    def as_sql(self, with_limits=True, with_col_aliases=False):
        query = self.query
        features = self.connection.features
        drop_for_update = (
            with_limits
            and getattr(query, "select_for_update", False)
            and (getattr(query, "high_mark", None) is not None or getattr(query, "low_mark", 0))
            and not getattr(features, "supports_select_for_update_with_limit", True)
        )
        if not drop_for_update:
            return original_as_sql(self, with_limits=with_limits, with_col_aliases=with_col_aliases)

        query.select_for_update = False
        try:
            return original_as_sql(self, with_limits=with_limits, with_col_aliases=with_col_aliases)
        finally:
            query.select_for_update = True

    SQLCompiler.as_sql = as_sql
    _SELECT_FOR_UPDATE_LIMIT_PATCHED = True


def list_locked_batch(queryset, batch_size, connection):
    """Evaluate a pk-ordered page and lock those rows when the backend allows it.

    Django raises ``NotSupportedError`` when ``select_for_update()`` is combined
    with ``LIMIT``/``OFFSET`` on backends such as Dameng
    (``supports_select_for_update_with_limit=False``). Those backends first
    collect the page of primary keys, then lock ``pk__in`` without a limit.
    """
    features = connection.features
    can_lock = features.has_select_for_update
    if can_lock and getattr(features, "supports_select_for_update_with_limit", True):
        return list(queryset.select_for_update()[:batch_size])

    pks = list(queryset.values_list("pk", flat=True)[:batch_size])
    if not pks:
        return []
    locked = queryset.filter(pk__in=pks)
    if can_lock:
        locked = locked.select_for_update()
    by_pk = {row.pk: row for row in locked}
    return [by_pk[pk] for pk in pks if pk in by_pk]
