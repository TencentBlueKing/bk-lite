"""Portable row-lock helpers for migrate_patch on frozen images.

``apps.core.utils.queryset_lock`` is the product API. Frozen WeOps X images
do not ship that module, so Dameng migrate_patch copies import this file
instead.
"""

import sys
from pathlib import Path

_SELECT_FOR_UPDATE_LIMIT_PATCHED = False
_SELECT_FOR_UPDATE_WINDOW_PATCHED = False
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


def _limited_for_update_unsupported(queryset) -> bool:
    query = getattr(queryset, "query", None)
    if query is None or not getattr(query, "select_for_update", False):
        return False
    if getattr(queryset, "_result_cache", None) is not None:
        return False
    from django.db import connections

    features = connections[queryset.db].features
    return not getattr(features, "supports_select_for_update_with_limit", True)


def _without_for_update(queryset):
    page = queryset._chain()
    page.query.select_for_update = False
    return page


def evaluate_locked_window(queryset, start: int, stop: int):
    """Lock a pk-ordered window without putting LIMIT and FOR UPDATE in one statement.

    The page of primary keys is read without a row lock. Those primary keys are
    then locked with ``pk__in``, which has no LIMIT. Row order follows the page.
    """
    if stop < start:
        return []
    page = _without_for_update(queryset)
    if start:
        pks = list(page.values_list("pk", flat=True)[start:stop])
    else:
        pks = list(page.values_list("pk", flat=True)[:stop])
    if not pks:
        return []
    locked = queryset.filter(pk__in=pks)
    by_pk = {row.pk: row for row in locked}
    return [by_pk[pk] for pk in pks if pk in by_pk]


def install_select_for_update_window_compat():
    """Rewrite limited ``select_for_update()`` on backends that reject LIMIT + FOR UPDATE.

    ``QuerySet.first()`` and ``queryset[:N]`` both set a limit. Celery claim
    loops use that shape. This keeps the row lock by paging primary keys, and
    it is installed for every Dameng process. The SQLCompiler workaround that
    drops FOR UPDATE stays limited to migrate and batch_init.
    """
    global _SELECT_FOR_UPDATE_WINDOW_PATCHED
    if _SELECT_FOR_UPDATE_WINDOW_PATCHED:
        return

    from django.db.models.query import QuerySet

    original_getitem = QuerySet.__getitem__
    original_exists = QuerySet.exists

    def __getitem__(self, key):
        if isinstance(key, slice) and key.stop is not None and key.step in (None, 1) and _limited_for_update_unsupported(self):
            start = 0 if key.start is None else int(key.start)
            return evaluate_locked_window(self, start, int(key.stop))
        if isinstance(key, int) and key >= 0 and _limited_for_update_unsupported(self):
            rows = evaluate_locked_window(self, key, key + 1)
            if not rows:
                raise IndexError
            return rows[0]
        return original_getitem(self, key)

    def exists(self):
        if self._result_cache is not None or not _limited_for_update_unsupported(self):
            return original_exists(self)
        # exists() compiles LIMIT 1. Lock that one row so the transaction still holds it.
        return bool(evaluate_locked_window(self, 0, 1))

    QuerySet.__getitem__ = __getitem__
    QuerySet.exists = exists
    _SELECT_FOR_UPDATE_WINDOW_PATCHED = True


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
