import importlib.util
import sys
import types
from pathlib import Path


def _install_module(monkeypatch, name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_module(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Logger:
    def info(self, *args, **kwargs):
        return None

    def debug(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None


class _Signal:
    def __init__(self):
        self.connected = []

    def connect(self, receiver, sender=None, weak=None, dispatch_uid=None):
        self.connected.append(
            {
                "receiver": receiver,
                "sender": sender,
                "weak": weak,
                "dispatch_uid": dispatch_uid,
            }
        )


class _CharField:
    def __init__(self, *args, **kwargs):
        self.attname = None
        self.column = None

    def contribute_to_class(self, cls, name, **kwargs):
        self.attname = name
        self.column = name

    def pre_save(self, model_instance, add):
        return getattr(model_instance, self.attname)

    def deconstruct(self):
        return self.attname, "apps.core.fields.s3_json_field.S3JSONField", [], {}

    def get_prep_value(self, value):
        return value

    def formfield(self, **kwargs):
        return kwargs


class _ModelsModule:
    CharField = _CharField


class _ContentFile:
    def __init__(self, content, name=None):
        self.content = content
        self.name = name


class _TransactionModule:
    def __init__(self):
        self.calls = []

    def on_commit(self, callback, using=None):
        self.calls.append({"callback": callback, "using": using})


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executed.append((query, params))

    def fetchone(self):
        if self.rows:
            return self.rows.pop(0)
        return None


class _Connection:
    class _Ops:
        @staticmethod
        def quote_name(value):
            return value

    def __init__(self, rows):
        self.rows = rows
        self.ops = self._Ops()
        self.cursors = []

    def cursor(self):
        cursor = _Cursor(self.rows)
        self.cursors.append(cursor)
        return cursor


class _Connections(dict):
    pass


class _Storage:
    def __init__(self):
        self.saved = []
        self.deleted = []

    def save(self, name, content):
        self.saved.append((name, content.name))
        return name

    def delete(self, path):
        self.deleted.append(path)

    def exists(self, file_path):
        return True

    def open(self, file_path, mode="rb"):
        raise AssertionError("open should not be called in these tests")


class _MinioBackendFactory:
    def __init__(self):
        self.instances = []

    def __call__(self, bucket_name=None):
        storage = _Storage()
        storage.bucket_name = bucket_name
        self.instances.append(storage)
        return storage


def _load_s3json_module(monkeypatch, rows_by_alias=None):
    signal = _Signal()
    transaction_module = _TransactionModule()
    rows_by_alias = rows_by_alias or {"default": []}
    connections = _Connections({alias: _Connection(rows) for alias, rows in rows_by_alias.items()})
    minio_factory = _MinioBackendFactory()

    _install_module(monkeypatch, "apps.core.logger", logger=_Logger())
    _install_module(monkeypatch, "django.core.files.base", ContentFile=_ContentFile)
    _install_module(monkeypatch, "django.db.models.signals", post_save=signal)
    _install_module(monkeypatch, "django.db.models", CharField=_CharField)
    _install_module(
        monkeypatch,
        "django.db",
        models=_ModelsModule(),
        connections=connections,
        transaction=transaction_module,
    )
    _install_module(monkeypatch, "django_minio_backend", MinioBackend=minio_factory)

    module = _load_module(
        "core_s3_json_field_test_module",
        Path(__file__).resolve().parents[1] / "fields" / "s3_json_field.py",
    )
    return module, signal, transaction_module, connections, minio_factory


def _build_instance(field, *, pk=1, db_alias="default", initial_value=None):
    class _Meta:
        db_table = "demo_table"
        pk = types.SimpleNamespace(column="id")

    instance = types.SimpleNamespace(pk=pk, _state=types.SimpleNamespace(db=db_alias), _meta=_Meta())
    instance.__dict__[field.attname] = initial_value
    return instance


def test_s3jsonfield_registers_post_save_signal_when_cleanup_enabled(monkeypatch):
    module, signal, _, _, _ = _load_s3json_module(monkeypatch)

    field = module.S3JSONField(bucket_name="bucket", delete_previous_on_update=True)

    class DemoModel:
        class _Meta:
            label_lower = "demo.model"

        _meta = _Meta()

    field.contribute_to_class(DemoModel, "payload")

    assert len(signal.connected) == 1
    assert signal.connected[0]["sender"] is DemoModel


def test_s3jsonfield_pre_save_registers_cleanup_task(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch, rows_by_alias={"default": [("old.json.gz",)]})
    field = module.S3JSONField(bucket_name="bucket", delete_previous_on_update=True)
    field.attname = "payload"
    field.column = "payload"
    instance = _build_instance(field, initial_value={"hello": "world"})

    new_path = field.pre_save(instance, add=False)

    assert new_path.endswith(".json.gz")
    tasks = getattr(instance, module.S3JSONField.CLEANUP_TASKS_ATTR)
    assert len(tasks) == 1
    assert tasks[0]["old_path"] == "old.json.gz"
    assert tasks[0]["new_path"] == new_path


def test_s3jsonfield_pre_save_skips_cleanup_when_disabled(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch, rows_by_alias={"default": [("old.json.gz",)]})
    field = module.S3JSONField(bucket_name="bucket")
    field.attname = "payload"
    field.column = "payload"
    instance = _build_instance(field, initial_value={"hello": "world"})

    field.pre_save(instance, add=False)

    assert not hasattr(instance, module.S3JSONField.CLEANUP_TASKS_ATTR)


def test_s3jsonfield_post_save_deletes_previous_object_on_commit(monkeypatch):
    module, _, transaction_module, _, _ = _load_s3json_module(monkeypatch)
    storage = _Storage()
    instance = types.SimpleNamespace(pk=7)
    setattr(
        instance,
        module.S3JSONField.CLEANUP_TASKS_ATTR,
        [{"field_name": "payload", "old_path": "old.json.gz", "new_path": "new.json.gz", "storage": storage, "using": "default"}],
    )

    sender = types.SimpleNamespace(_meta=types.SimpleNamespace(label="demo.Model"))
    module._handle_s3jsonfield_post_save_cleanup(sender, instance)

    assert len(transaction_module.calls) == 1
    assert transaction_module.calls[0]["using"] == "default"
    transaction_module.calls[0]["callback"]()
    assert storage.deleted == ["old.json.gz"]
    assert getattr(instance, module.S3JSONField.CLEANUP_TASKS_ATTR) == []


def test_s3jsonfield_post_save_uses_instance_db_alias(monkeypatch):
    module, _, transaction_module, _, _ = _load_s3json_module(monkeypatch)
    storage = _Storage()
    instance = types.SimpleNamespace(pk=9)
    setattr(
        instance,
        module.S3JSONField.CLEANUP_TASKS_ATTR,
        [{"field_name": "payload", "old_path": "old.json.gz", "new_path": "new.json.gz", "storage": storage, "using": "analytics"}],
    )

    sender = types.SimpleNamespace(_meta=types.SimpleNamespace(label="demo.Model"))
    module._handle_s3jsonfield_post_save_cleanup(sender, instance)

    assert transaction_module.calls[0]["using"] == "analytics"


def test_s3jsonfield_descriptor_assignment_defers_upload_until_pre_save(monkeypatch):
    module, _, _, _, minio_factory = _load_s3json_module(monkeypatch)
    field = module.S3JSONField(bucket_name="bucket", delete_previous_on_update=True)

    class DemoModel:
        class _Meta:
            label_lower = "demo.model"

        _meta = _Meta()

    field.contribute_to_class(DemoModel, "payload")

    instance = DemoModel()
    instance._state = types.SimpleNamespace(db="default")
    instance._meta = types.SimpleNamespace(db_table="demo_table", pk=types.SimpleNamespace(column="id"))
    instance.pk = 1
    instance.__dict__[field.attname] = "existing.json.gz"
    instance.payload = {"hello": "world"}

    assert instance.__dict__[field.attname] == "existing.json.gz"
    pending_name = field._pending_value_attr_name
    assert instance.__dict__[pending_name] == {"hello": "world"}
    assert minio_factory.instances == []


def test_s3jsonfield_pre_save_uses_pending_assigned_value(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch, rows_by_alias={"default": [("old.json.gz",)]})
    field = module.S3JSONField(bucket_name="bucket", delete_previous_on_update=True)
    field.attname = "payload"
    field.column = "payload"
    instance = _build_instance(field, initial_value="current.json.gz")
    instance.__dict__[field._pending_value_attr_name] = {"hello": "world"}

    new_path = field.pre_save(instance, add=False)

    assert new_path.endswith(".json.gz")
    assert instance.__dict__[field.attname] == new_path
    assert field._pending_value_attr_name not in instance.__dict__
    tasks = getattr(instance, module.S3JSONField.CLEANUP_TASKS_ATTR)
    assert tasks[0]["old_path"] == "old.json.gz"


def test_pre_save_does_not_leave_residual_pending(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch, rows_by_alias={"default": [("old.json.gz",)]})
    field = module.S3JSONField(bucket_name="bucket", delete_previous_on_update=True)
    field.attname = "payload"
    field.column = "payload"
    instance = _build_instance(field, initial_value="current.json.gz")
    instance.__dict__[field._pending_value_attr_name] = [{"metric": "cpu"}]

    field.pre_save(instance, add=False)

    assert field._pending_value_attr_name not in instance.__dict__


def test_from_db_value_returns_path_string_without_downloading(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch)
    field = module.S3JSONField(bucket_name="bucket")
    field.attname = "payload"

    result = field.from_db_value("snapshots/abc.json.gz", None, None)

    assert result == "snapshots/abc.json.gz"


def test_from_db_value_returns_none_for_empty(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch)
    field = module.S3JSONField(bucket_name="bucket")
    field.attname = "payload"

    assert field.from_db_value("", None, None) is None
    assert field.from_db_value(None, None, None) is None


def test_pre_save_preserves_path_when_value_is_none(monkeypatch):
    module, _, _, _, _ = _load_s3json_module(monkeypatch, rows_by_alias={"default": []})
    field = module.S3JSONField(bucket_name="bucket")
    field.attname = "payload"
    field.column = "payload"
    instance = _build_instance(field, initial_value="snapshots/existing.json.gz")

    result = field.pre_save(instance, add=False)

    assert result == "snapshots/existing.json.gz"
