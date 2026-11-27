from types import SimpleNamespace

import pytest

from apps.core.utils.queryset_lock import is_schema_init_process, list_locked_batch

pytestmark = pytest.mark.unit


class _FakeValues(list):
    def __init__(self, pks, events):
        super().__init__(pks)
        self.events = events

    def __getitem__(self, key):
        self.events.append(("values_slice", key))
        return list(super().__getitem__(key))


class _FakeQuerySet:
    def __init__(self, rows, *, events=None, locked=False):
        self.rows = rows
        self.events = events if events is not None else []
        self.locked = locked

    def select_for_update(self):
        self.events.append("select_for_update")
        return _FakeQuerySet(self.rows, events=self.events, locked=True)

    def values_list(self, field, flat=False):
        self.events.append(("values_list", field, flat))
        return _FakeValues([row.pk for row in self.rows], self.events)

    def filter(self, **kwargs):
        self.events.append(("filter", kwargs))
        allowed = set(kwargs.get("pk__in", [row.pk for row in self.rows]))
        return _FakeQuerySet([row for row in self.rows if row.pk in allowed], events=self.events, locked=self.locked)

    def __getitem__(self, key):
        self.events.append(("slice", key))
        return _FakeQuerySet(self.rows[key], events=self.events, locked=self.locked)

    def __iter__(self):
        return iter(self.rows)


def _rows(*pks):
    return [SimpleNamespace(pk=pk) for pk in pks]


def test_list_locked_batch_uses_limit_with_for_update_when_backend_allows_it():
    queryset = _FakeQuerySet(_rows(1, 2, 3))
    connection = SimpleNamespace(features=SimpleNamespace(has_select_for_update=True, supports_select_for_update_with_limit=True))

    result = list_locked_batch(queryset, 2, connection)

    assert [row.pk for row in result] == [1, 2]
    assert queryset.events == ["select_for_update", ("slice", slice(None, 2))]


def test_list_locked_batch_locks_by_pk_when_limit_is_unsupported():
    queryset = _FakeQuerySet(_rows(1, 2, 3))
    connection = SimpleNamespace(features=SimpleNamespace(has_select_for_update=True, supports_select_for_update_with_limit=False))

    result = list_locked_batch(queryset, 2, connection)

    assert [row.pk for row in result] == [1, 2]
    assert queryset.events == [
        ("values_list", "pk", True),
        ("values_slice", slice(None, 2)),
        ("filter", {"pk__in": [1, 2]}),
        "select_for_update",
    ]


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["python3", "manage.py", "migrate"], True),
        (["python3", "manage.py", "batch_init", "--apps=cmdb"], True),
        (["python3", "/apps/manage.py", "migrate", "--noinput"], True),
        (["uvicorn", "asgi:application", "--host", "0.0.0.0"], False),
        (["celery", "-A", "config", "worker"], False),
        (["gunicorn", "wsgi:application"], False),
    ],
)
def test_is_schema_init_process_matches_only_migrate_and_batch_init(argv, expected):
    assert is_schema_init_process(argv) is expected


def test_list_locked_batch_skips_lock_when_backend_has_no_select_for_update():
    queryset = _FakeQuerySet(_rows(4, 5))
    connection = SimpleNamespace(features=SimpleNamespace(has_select_for_update=False))

    result = list_locked_batch(queryset, 10, connection)

    assert [row.pk for row in result] == [4, 5]
    assert "select_for_update" not in queryset.events
    assert ("values_slice", slice(None, 10)) in queryset.events
