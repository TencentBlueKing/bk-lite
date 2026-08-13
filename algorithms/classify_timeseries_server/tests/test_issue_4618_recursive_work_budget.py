"""Issue #4618：递归特征工程在进入模型前受组合工作量预算保护。"""

import numpy as np
import pandas as pd
import pytest

from classify_timeseries_server.serving.prediction_budget import (
    RecursiveFeatureEngineeringBudgetExceeded,
    enforce_recursive_feature_engineering_budget,
    estimate_recursive_feature_engineering_work,
)
from classify_timeseries_server.training.preprocessing.feature_engineering import (
    TimeSeriesFeatureEngineer,
)


WRAPPER_MODULE = "classify_timeseries_server.training.models"


def make_wrapper(
    name="GradientBoostingWrapper",
    use_feature_engineering=True,
    has_feature_engineer=True,
):
    wrapper_type = type(name, (), {"__module__": f"{WRAPPER_MODULE}.test_wrapper"})
    wrapper = wrapper_type()
    wrapper.use_feature_engineering = use_feature_engineering
    wrapper.feature_engineer = object() if has_feature_engineer else None
    return wrapper


class LoadedPyFuncModel:
    """模拟 MLflow PyFuncModel 对 Python wrapper 的封装。"""

    def __init__(self, python_model):
        self.python_model = python_model

    def unwrap_python_model(self):
        return self.python_model


class UnreadablePyFuncModel:
    """模拟无法解包的旧/第三方 MLflow 制品。"""

    def unwrap_python_model(self):
        raise RuntimeError("unsupported artifact")


class LegacyPyFuncModel(UnreadablePyFuncModel):
    """模拟公开解包不可用、但仍保留历史内部结构的 MLflow 制品。"""

    def __init__(self, python_model):
        self._model_impl = type("LegacyModelImpl", (), {})()
        self._model_impl.python_model = python_model


def test_estimate_includes_recursive_history_growth():
    assert estimate_recursive_feature_engineering_work(100, 4) == 406


@pytest.mark.parametrize("name", ["GradientBoostingWrapper", "RandomForestWrapper"])
@pytest.mark.parametrize("wrapped", [False, True])
def test_budget_accepts_boundary_and_rejects_next_unit(name, wrapped):
    model = make_wrapper(name)
    if wrapped:
        model = LoadedPyFuncModel(model)

    enforce_recursive_feature_engineering_budget(
        model, history_points=100, steps=4, limit=406
    )

    with pytest.raises(RecursiveFeatureEngineeringBudgetExceeded) as error:
        enforce_recursive_feature_engineering_budget(
            model, history_points=100, steps=4, limit=405
        )

    assert error.value.history_points == 100
    assert error.value.steps == 4
    assert error.value.estimated_work == 406
    assert error.value.limit == 405


def test_maximum_individual_limits_are_rejected():
    model = LoadedPyFuncModel(make_wrapper())

    with pytest.raises(RecursiveFeatureEngineeringBudgetExceeded):
        enforce_recursive_feature_engineering_budget(
            model,
            history_points=50_000,
            steps=1_000,
            limit=2_000_000,
        )


def test_legacy_mlflow_model_is_still_protected():
    model = LegacyPyFuncModel(make_wrapper())

    with pytest.raises(RecursiveFeatureEngineeringBudgetExceeded):
        enforce_recursive_feature_engineering_budget(
            model,
            history_points=50_000,
            steps=1_000,
            limit=2_000_000,
        )


@pytest.mark.parametrize(
    "model",
    [
        make_wrapper(use_feature_engineering=False),
        make_wrapper(has_feature_engineer=False),
        make_wrapper(name="ProphetWrapper"),
        make_wrapper(name="DummyModel"),
        UnreadablePyFuncModel(),
        object(),
    ],
)
def test_budget_does_not_limit_other_prediction_algorithms(model):
    enforce_recursive_feature_engineering_budget(
        model, history_points=50_000, steps=1_000, limit=1
    )


def test_high_dynamic_range_rolling_std_requires_full_history():
    """锁住曾推翻尾部截断方案的数值反例。"""
    rng = np.random.default_rng(4618)
    values = 1e12 + rng.normal(size=50_000)
    history = pd.Series(
        values,
        index=pd.date_range("2020-01-01", periods=len(values), freq="h"),
    )
    engineer = TimeSeriesFeatureEngineer(
        lag_periods=[1],
        rolling_windows=[1_000],
        rolling_features=["std"],
        use_temporal_features=False,
        use_cyclical_features=False,
        use_diff_features=False,
        drop_na=True,
    ).fit(history)

    full_features, _ = engineer.transform(history)
    tail_features, _ = engineer.transform(history.iloc[-1_001:])
    column = "value_window_1000_std"

    assert np.float32(full_features.iloc[-1][column]) != np.float32(
        tail_features.iloc[-1][column]
    )
