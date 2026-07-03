from django.db.models import QuerySet

from apps.core.db_patches import dameng


class _Field:
    def __init__(self, name, *, unique=False):
        self.name = name
        self.attname = name
        self.unique = unique


class _Meta:
    pk = _Field("id")
    concrete_fields = (pk, _Field("name", unique=True), _Field("team_id"))
    unique_together = (("team_id", "name"),)
    constraints = ()

    def get_field(self, name):
        return next(field for field in self.concrete_fields if field.name == name or field.attname == name)


class _Model:
    _meta = _Meta()


class _Obj:
    def __init__(self, *, id=None, name, team_id=1):
        self.id = id
        self.pk = id
        self.name = name
        self.team_id = team_id
        self.save_calls = []

    def save(self, using=None):
        self.save_calls.append(using)


class _ValuesQuerySet:
    def __init__(self, rows):
        self.rows = rows

    def values_list(self, *field_names):
        return [tuple(row[field_name] for field_name in field_names) for row in self.rows]


class _QuerySet:
    model = _Model
    db = "default"

    def __init__(self, rows=None):
        self.rows = rows or []
        self.filters = []

    def filter(self, query):
        self.filters.append(query)
        return _ValuesQuerySet(self.rows)


def test_filter_bulk_create_conflicts_skips_existing_and_batch_duplicates():
    queryset = _QuerySet(rows=[{"id": 100, "name": "exists", "team_id": 1}])
    objs = [
        _Obj(name="exists", team_id=1),
        _Obj(name="new", team_id=1),
        _Obj(name="new", team_id=1),
        _Obj(name="other", team_id=2),
    ]

    filtered = dameng._filter_bulk_create_conflicts(queryset, objs)

    assert filtered == [objs[1], objs[3]]


def test_ignore_conflicts_patch_keeps_bulk_create_path(monkeypatch):
    bulk_create_calls = []

    def original_bulk_create(self, objs, **kwargs):
        bulk_create_calls.append({"objs": list(objs), "kwargs": kwargs})
        return list(objs)

    monkeypatch.setattr(QuerySet, "bulk_create", original_bulk_create)
    dameng._patch_bulk_create_ignore_conflicts()

    objs = [_Obj(name="a"), _Obj(name="b")]
    created = QuerySet.bulk_create(_QuerySet(), objs, ignore_conflicts=True, batch_size=500)

    assert created == objs
    assert [obj.save_calls for obj in objs] == [[], []]
    assert bulk_create_calls == [
        {
            "objs": objs,
            "kwargs": {
                "batch_size": 500,
                "ignore_conflicts": False,
                "update_conflicts": False,
                "update_fields": None,
                "unique_fields": None,
            },
        }
    ]
