"""Issue #4494：Spell MLflow/pyfunc 制品不得携带训练日志原文。"""

from unittest.mock import patch

import cloudpickle

from classify_log_server.training.models.spell_model import SpellModel
from classify_log_server.training.models.spell_wrapper import (
    SpellWrapper,
    log_spell_model_to_mlflow,
)

# 多空格哨兵只存在于 raw_logs 原文；tokenize/join 会折叠空格，模板中不会原样出现。
SENTINEL = "ISSUE4494_SENTINEL   unique-raw-log-leak"


def _fit_with_sentinel() -> SpellModel:
    model = SpellModel(tau=0.5)
    model.fit(
        [
            "database connection failed host alpha",
            "database connection failed host beta",
            f"user login succeeded account {SENTINEL}",
            "user login succeeded account bob",
        ],
        verbose=False,
        log_to_mlflow=False,
    )
    return model


def _payload_contains_sentinel(payload: bytes) -> bool:
    return SENTINEL.encode() in payload


def _raw_logs_contain_sentinel(model: SpellModel) -> bool:
    return any(SENTINEL in log for log in model.raw_logs)


def test_spell_wrapper_of_training_model_serializes_raw_log_sentinel():
    """RED 证据：直接封装训练中模型会把原文打进 pickle。"""
    model = _fit_with_sentinel()

    assert _raw_logs_contain_sentinel(model)
    assert _payload_contains_sentinel(cloudpickle.dumps(SpellWrapper(model=model)))


def test_save_mlflow_logs_inference_copy_without_training_raw_logs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    model = _fit_with_sentinel()
    captured = {}

    def fake_log_model(**kwargs):
        captured.update(kwargs)

    with patch("mlflow.pyfunc.log_model", side_effect=fake_log_model):
        model.save_mlflow(artifact_path="model")

    python_model = captured["python_model"]
    assert isinstance(python_model, SpellWrapper)
    assert python_model.model.raw_logs == []
    assert not _payload_contains_sentinel(cloudpickle.dumps(python_model))
    assert _raw_logs_contain_sentinel(model)


def test_log_spell_model_to_mlflow_logs_inference_copy_without_training_raw_logs():
    model = _fit_with_sentinel()
    captured = {}

    def fake_log_model(**kwargs):
        captured.update(kwargs)

    with patch("mlflow.pyfunc.log_model", side_effect=fake_log_model):
        log_spell_model_to_mlflow(model, artifact_path="model")

    python_model = captured["python_model"]
    assert isinstance(python_model, SpellWrapper)
    assert python_model.model.raw_logs == []
    assert not _payload_contains_sentinel(cloudpickle.dumps(python_model))
    assert _raw_logs_contain_sentinel(model)


def test_inference_copy_keeps_training_raw_logs_and_matches_predict_templates():
    model = _fit_with_sentinel()
    inference = model.for_inference()

    assert inference is not model
    assert inference.raw_logs == []
    assert inference.lcs_cache == {}
    assert _raw_logs_contain_sentinel(model)
    assert model.lcs_cache is not inference.lcs_cache
    assert model.raw_logs is not inference.raw_logs

    probe_logs = [
        "database connection failed host gamma",
        "user login succeeded account carol",
    ]
    assert inference.predict(probe_logs) == model.predict(probe_logs)
    assert inference.get_templates() == model.get_templates()
