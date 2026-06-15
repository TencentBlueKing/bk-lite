import sys
import types
from importlib import util
from pathlib import Path


def _restore_modules(previous):
    for name, original in previous.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


def test_import_does_not_replace_django_db_modules():
    module_path = Path(__file__).with_name("test_anthropic_protocol.py")
    module_name = "isolated_test_anthropic_protocol_import"

    sentinel_db = types.ModuleType("django.db")
    sentinel_models = types.ModuleType("django.db.models")
    sentinel_transaction = types.ModuleType("django.db.transaction")
    sentinel_db.models = sentinel_models
    sentinel_db.transaction = sentinel_transaction

    previous = {
        "django.db": sys.modules.get("django.db"),
        "django.db.models": sys.modules.get("django.db.models"),
        "django.db.transaction": sys.modules.get("django.db.transaction"),
        module_name: sys.modules.get(module_name),
    }

    sys.modules["django.db"] = sentinel_db
    sys.modules["django.db.models"] = sentinel_models
    sys.modules["django.db.transaction"] = sentinel_transaction

    try:
        spec = util.spec_from_file_location(module_name, module_path)
        module = util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)

        assert sys.modules["django.db"] is sentinel_db
        assert sys.modules["django.db.models"] is sentinel_models
        assert sys.modules["django.db.transaction"] is sentinel_transaction
    finally:
        _restore_modules(previous)
