"""测试 _load_from_local 的 SHA256 完整性校验（Issue #3535）.

log server 有 SpellModel-first 的分支，joblib 是 fallback。
使用独立 exec harness 桩掉 SpellModel 路径，只测 joblib fallback 的校验逻辑。
"""

import hashlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

LOADER_PATH = str(
    Path(__file__).parent.parent
    / "classify_log_server"
    / "serving"
    / "models"
    / "loader.py"
)


def _install_stub(name, **attrs):
    parts = name.split(".")
    for i in range(1, len(parts)):
        pn = ".".join(parts[:i])
        if pn not in sys.modules:
            sys.modules[pn] = types.ModuleType(pn)
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _load_fn():
    _install_stub("loguru", logger=MagicMock())
    _install_stub("dummy_model_stub", DummyModel=MagicMock)

    source = Path(LOADER_PATH).read_text()
    # SpellModel 路径用桩替换（模拟 non-spell model，走 joblib fallback）
    source = (
        source
        .replace("from ..config import ModelConfig", "ModelConfig = None")
        .replace("from .dummy_model import DummyModel", "from dummy_model_stub import DummyModel")
        .replace(
            "from ...training.models.spell_model import SpellModel",
            "raise ImportError('stub: not a spell model')",
        )
        .replace("from ...training.models.spell_wrapper import SpellWrapper", "")
    )
    ns = {}
    exec(compile(source, LOADER_PATH, "exec"), ns)
    return ns["_load_from_local"]


class FakeConfig:
    source = "local"
    mlflow_model_uri = None
    mlflow_tracking_uri = None

    def __init__(self, model_path):
        self.model_path = model_path


@pytest.fixture()
def load_from_local():
    return _load_fn()


@pytest.fixture()
def mock_joblib():
    mock = MagicMock()
    mock.load.return_value = object()
    _install_stub("joblib", load=mock.load)
    return mock


def test_checksum_match_allows_joblib_load(tmp_path, monkeypatch, load_from_local, mock_joblib):
    """MODEL_SHA256 正确时 joblib.load 应被调用（log server joblib fallback 路径）。"""
    f = tmp_path / "model.pkl"
    f.write_bytes(b"legit-log-model")
    monkeypatch.setenv("MODEL_SHA256", hashlib.sha256(b"legit-log-model").hexdigest())

    load_from_local(FakeConfig(str(f)))

    assert mock_joblib.load.called, "joblib.load must be called when checksum matches"


def test_checksum_mismatch_blocks_joblib_load(tmp_path, monkeypatch, load_from_local, mock_joblib):
    """MODEL_SHA256 不匹配时 joblib.load 绝对不能被调用。"""
    f = tmp_path / "model.pkl"
    f.write_bytes(b"tampered-log-model")
    monkeypatch.setenv("MODEL_SHA256", "c" * 64)
    monkeypatch.setenv("ALLOW_DUMMY_FALLBACK", "false")

    with pytest.raises(RuntimeError, match="local path"):
        load_from_local(FakeConfig(str(f)))

    assert not mock_joblib.load.called, (
        "joblib.load MUST NOT execute when checksum mismatches in log server — "
        "reverting this means the RCE guard is absent!"
    )


def test_no_model_sha256_env_backward_compatible(tmp_path, monkeypatch, load_from_local, mock_joblib):
    """未配置 MODEL_SHA256 时应向后兼容，仍执行加载。"""
    f = tmp_path / "model.pkl"
    f.write_bytes(b"compat-log-model")
    monkeypatch.delenv("MODEL_SHA256", raising=False)

    load_from_local(FakeConfig(str(f)))

    assert mock_joblib.load.called, "Without MODEL_SHA256, joblib.load must still run for backward compat"
