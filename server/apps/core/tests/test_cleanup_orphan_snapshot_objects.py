import importlib.util
import io
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


class _BaseCommand:
    class _Style:
        @staticmethod
        def SUCCESS(message):
            return message

    def __init__(self):
        self.stdout = types.SimpleNamespace(write=lambda message: None)
        self.style = self._Style()


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query):
        self.query = query

    def fetchall(self):
        return self.rows


class _Connection:
    class _Ops:
        @staticmethod
        def quote_name(value):
            return value

    def __init__(self, rows):
        self.rows = rows
        self.ops = self._Ops()

    def cursor(self):
        return _Cursor(self.rows)


class _Storage:
    def __init__(self, bucket, objects):
        self.bucket = bucket
        self.deleted = []
        self.client = types.SimpleNamespace(list_objects=lambda bucket, recursive=True: iter(objects))

    def delete(self, path):
        self.deleted.append(path)


class _Object:
    def __init__(self, object_name, size):
        self.object_name = object_name
        self.size = size


def _build_model(name, table, field_name, storage):
    field = types.SimpleNamespace(column=field_name, storage=storage)

    class _Meta:
        db_table = table

        @staticmethod
        def get_field(requested_name):
            assert requested_name == field_name
            return field

    return types.SimpleNamespace(__name__=name, _meta=_Meta())


def _load_command_module(monkeypatch, *, monitor_rows, log_rows, monitor_objects, log_objects):
    monitor_storage = _Storage("monitor-alert-raw-data", monitor_objects)
    log_storage = _Storage("log-alert-raw-data", log_objects)
    monitor_model = _build_model("MonitorAlertMetricSnapshot", "monitor_snapshot_table", "snapshots", monitor_storage)
    log_model = _build_model("AlertSnapshot", "log_snapshot_table", "snapshots", log_storage)

    _install_module(monkeypatch, "django.core.management.base", BaseCommand=_BaseCommand)
    _install_module(
        monkeypatch,
        "django.db",
        connections={"monitor": _Connection(monitor_rows), "log": _Connection(log_rows)},
        router=types.SimpleNamespace(db_for_read=lambda model: "monitor" if model is monitor_model else "log"),
    )
    _install_module(monkeypatch, "apps.monitor.models.monitor_policy", MonitorAlertMetricSnapshot=monitor_model)
    _install_module(monkeypatch, "apps.log.models.policy", AlertSnapshot=log_model)

    module = _load_module(
        "cleanup_orphan_snapshot_objects_test_module",
        Path(__file__).resolve().parents[1] / "management" / "commands" / "cleanup_orphan_snapshot_objects.py",
    )
    command = module.Command()
    output = io.StringIO()
    command.stdout = types.SimpleNamespace(write=lambda message: output.write(f"{message}\n"))
    return command, output, monitor_storage, log_storage


def test_cleanup_orphan_snapshot_objects_dry_run(monkeypatch):
    command, output, monitor_storage, log_storage = _load_command_module(
        monkeypatch,
        monitor_rows=[("2026/05/01/monitoralertmetricsnapshot_1_keep.json.gz",)],
        log_rows=[("2026/05/01/alertsnapshot_1_keep.json.gz",)],
        monitor_objects=[
            _Object("2026/05/01/monitoralertmetricsnapshot_1_keep.json.gz", 10),
            _Object("2026/05/01/monitoralertmetricsnapshot_1_old.json.gz", 20),
        ],
        log_objects=[
            _Object("2026/05/01/alertsnapshot_1_keep.json.gz", 11),
            _Object("2026/05/01/alertsnapshot_1_old.json.gz", 21),
        ],
    )

    command.handle(target="all", delete=False, limit=5)

    assert monitor_storage.deleted == []
    assert log_storage.deleted == []
    text = output.getvalue()
    assert "orphans=1" in text
    assert "sample orphan: 2026/05/01/monitoralertmetricsnapshot_1_old.json.gz (20 bytes)" in text
    assert "sample orphan: 2026/05/01/alertsnapshot_1_old.json.gz (21 bytes)" in text


def test_cleanup_orphan_snapshot_objects_delete_mode(monkeypatch):
    command, output, monitor_storage, log_storage = _load_command_module(
        monkeypatch,
        monitor_rows=[("2026/05/01/monitoralertmetricsnapshot_1_keep.json.gz",)],
        log_rows=[],
        monitor_objects=[
            _Object("2026/05/01/monitoralertmetricsnapshot_1_keep.json.gz", 10),
            _Object("2026/05/01/monitoralertmetricsnapshot_1_old.json.gz", 20),
        ],
        log_objects=[],
    )

    command.handle(target="monitor", delete=True, limit=1)

    assert monitor_storage.deleted == ["2026/05/01/monitoralertmetricsnapshot_1_old.json.gz"]
    assert log_storage.deleted == []
    assert "deleted=1" in output.getvalue()
