"""Regression tests for explicit model-source fallback policy (Issue #3850)."""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

LOADER_PATH = Path(__file__).parent.parent / "classify_log_server" / "serving" / "models" / "loader.py"


class DummyModel:
    pass


def _install_stub(name: str, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_namespace():
    _install_stub("loguru", logger=MagicMock())
    _install_stub("dotenv", load_dotenv=lambda: None)
    _install_stub("dummy_model_stub", DummyModel=DummyModel)
    source = LOADER_PATH.read_text()
    source = (
        source.replace("from ..config import ModelConfig", "ModelConfig = None")
        .replace("from .dummy_model import DummyModel", "from dummy_model_stub import DummyModel")
        .replace("from dotenv import load_dotenv", "")
        .replace("load_dotenv()", "")
    )
    namespace = {}
    exec(compile(source, str(LOADER_PATH), "exec"), namespace)
    return namespace


def _config(source: str, *, model_path=None, mlflow_model_uri=None):
    return types.SimpleNamespace(
        source=source,
        model_path=model_path,
        mlflow_tracking_uri=None,
        mlflow_model_uri=mlflow_model_uri,
    )


@pytest.mark.parametrize("source", ["mlflow", "local"])
def test_explicit_source_without_location_fails_when_fallback_disabled(monkeypatch, source):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "false")

    with pytest.raises(ValueError):
        _load_namespace()["load_model"](_config(source))


def test_mlflow_load_error_fails_when_fallback_disabled(monkeypatch):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "false")
    _install_stub(
        "mlflow",
        set_tracking_uri=MagicMock(),
        pyfunc=types.SimpleNamespace(load_model=MagicMock(side_effect=OSError("unavailable"))),
    )

    with pytest.raises(RuntimeError, match="MLflow"):
        _load_namespace()["load_model"](_config("mlflow", mlflow_model_uri="models:/demo/1"))


def test_mlflow_load_error_uses_dummy_when_fallback_enabled(monkeypatch):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "true")
    _install_stub(
        "mlflow",
        set_tracking_uri=MagicMock(),
        pyfunc=types.SimpleNamespace(load_model=MagicMock(side_effect=OSError("unavailable"))),
    )

    model = _load_namespace()["load_model"](_config("mlflow", mlflow_model_uri="models:/demo/1"))

    assert isinstance(model, DummyModel)


def test_local_load_error_fails_when_fallback_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "false")
    _install_stub("joblib", load=MagicMock())

    with pytest.raises(RuntimeError, match="local path"):
        _load_namespace()["load_model"](_config("local", model_path=str(tmp_path / "missing-model")))


def test_local_load_error_uses_dummy_when_fallback_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "true")
    _install_stub("joblib", load=MagicMock())

    model = _load_namespace()["load_model"](_config("local", model_path=str(tmp_path / "missing-model")))

    assert isinstance(model, DummyModel)


def test_dummy_source_remains_explicitly_available(monkeypatch):
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "false")

    assert isinstance(_load_namespace()["load_model"](_config("dummy")), DummyModel)
