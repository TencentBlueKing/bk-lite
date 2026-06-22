"""时间序列预测服务 schema 校验和 predict 路径的单元测试。

覆盖：
- TimeSeriesPoint / PredictionConfig / PredictRequest 的 schema 校验
- PredictRequest.to_series() 的基本行为
- DummyModel.predict() 的输入/输出 shape 不变量（步数）
- MLService.predict() 的验证失败路径和正常预测路径（使用 DummyModel）
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 向 sys.modules 注入最小化 BentoML 存根
# ---------------------------------------------------------------------------

def _stub_bentoml():
    bentoml = types.ModuleType("bentoml")

    def service(**kwargs):
        def decorator(cls):
            return cls
        return decorator

    def api(fn=None, **kwargs):
        if fn is not None:
            return fn
        return lambda f: f

    def on_deployment(fn):
        return fn

    def on_shutdown(fn):
        return fn

    bentoml.service = service
    bentoml.api = api
    bentoml.on_deployment = on_deployment
    bentoml.on_shutdown = on_shutdown

    # exceptions 子模块
    bentoml_exceptions = types.ModuleType("bentoml.exceptions")

    class BentoMLException(Exception):
        error_code = 500

    bentoml_exceptions.BentoMLException = BentoMLException
    bentoml.exceptions = bentoml_exceptions

    # metrics 子模块
    bentoml_metrics = types.ModuleType("bentoml.metrics")

    def _make_counter(**kwargs):
        m = MagicMock()
        m.labels.return_value = m
        return m

    def _make_histogram(**kwargs):
        m = MagicMock()
        m.labels.return_value = m
        return m

    bentoml_metrics.Counter = _make_counter
    bentoml_metrics.Histogram = _make_histogram
    bentoml.metrics = bentoml_metrics

    sys.modules.setdefault("bentoml", bentoml)
    sys.modules.setdefault("bentoml.exceptions", bentoml_exceptions)
    sys.modules.setdefault("bentoml.metrics", bentoml_metrics)


# mlflow stub（timeseries service 在 import 层引用）
def _stub_mlflow():
    mlflow = types.ModuleType("mlflow")
    mlflow.sklearn = types.ModuleType("mlflow.sklearn")
    sys.modules.setdefault("mlflow", mlflow)
    sys.modules.setdefault("mlflow.sklearn", mlflow.sklearn)


_stub_bentoml()
_stub_mlflow()


from classify_timeseries_server.serving.schemas.api_schema import (  # noqa: E402
    PredictRequest,
    PredictResponse,
    PredictionConfig,
    TimeSeriesPoint,
)
from classify_timeseries_server.serving.models.dummy_model import DummyModel  # noqa: E402


# ---------------------------------------------------------------------------
# Schema 校验测试
# ---------------------------------------------------------------------------


class TestTimeSeriesPointSchema:
    def test_valid_point(self):
        pt = TimeSeriesPoint(timestamp=1700000000, value=3.14)
        assert pt.value == pytest.approx(3.14)

    def test_missing_timestamp_raises(self):
        with pytest.raises(ValidationError):
            TimeSeriesPoint(value=1.0)

    def test_missing_value_raises(self):
        with pytest.raises(ValidationError):
            TimeSeriesPoint(timestamp=1700000000)


class TestPredictionConfigSchema:
    """steps 必须 > 0（gt=0 约束）。"""

    def test_valid_steps(self):
        cfg = PredictionConfig(steps=5)
        assert cfg.steps == 5

    def test_zero_steps_raises(self):
        with pytest.raises(ValidationError):
            PredictionConfig(steps=0)

    def test_negative_steps_raises(self):
        with pytest.raises(ValidationError):
            PredictionConfig(steps=-1)

    def test_missing_steps_raises(self):
        with pytest.raises(ValidationError):
            PredictionConfig()


class TestPredictRequestToSeries:
    def _make_request(self, pairs, steps=3):
        points = [TimeSeriesPoint(timestamp=t, value=v) for t, v in pairs]
        return PredictRequest(data=points, config=PredictionConfig(steps=steps))

    def test_basic_conversion(self):
        req = self._make_request([(1000, 1.0), (2000, 2.0), (3000, 3.0)])
        series = req.to_series()
        assert len(series) == 3

    def test_values_preserved(self):
        req = self._make_request([(1000, 10.5), (2000, 20.5)])
        series = req.to_series()
        assert list(series.values) == [10.5, 20.5]


# ---------------------------------------------------------------------------
# DummyModel 单元测试
# ---------------------------------------------------------------------------


class TestDummyModel:
    """DummyModel.predict() 的时间序列格式输出不变量。"""

    def setup_method(self):
        self.model = DummyModel()

    def test_output_length_equals_steps(self):
        """输出列表长度必须等于请求的 steps 数。"""
        result = self.model.predict({"history": [1.0, 2.0, 3.0], "steps": 7})
        assert len(result) == 7

    def test_naive_forecast_repeats_last_value(self):
        """DummyModel 使用 naive forecast（重复最后一个值）。"""
        history = [1.0, 2.0, 5.0]
        result = self.model.predict({"history": history, "steps": 4})
        assert all(v == pytest.approx(5.0) for v in result)

    def test_empty_history_returns_zeros(self):
        result = self.model.predict({"history": [], "steps": 3})
        assert len(result) == 3
        assert all(v == pytest.approx(0.0) for v in result)

    def test_single_step(self):
        result = self.model.predict({"history": [42.0], "steps": 1})
        assert len(result) == 1
        assert result[0] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# MLService.predict() 路径测试（注入 DummyModel，不启动真实 BentoML）
# ---------------------------------------------------------------------------


class TestMLServicePredict:
    def _make_service(self, steps=3):
        from classify_timeseries_server.serving.service import MLService

        svc = object.__new__(MLService)

        # 使用 MagicMock 替代 DummyModel，避免 DummyModel 对 pd.Series 类型的 history
        # 做 bool 检查时触发 Series ambiguous truth value 问题
        mock_model = MagicMock()
        mock_model.predict.return_value = [1.0] * steps
        svc.model = mock_model

        config = MagicMock()
        config.source = "dummy"
        config.mlflow_model_uri = None
        config.model_path = None
        svc.config = config
        return svc

    @pytest.mark.asyncio
    async def test_predict_success_returns_correct_steps(self):
        """正常请求：返回的 prediction 点数等于 steps。

        Revert 验证：若修改 predicted_points 构建逻辑（如 range(1, steps+1)），
        此 test 将因 len(prediction) != steps 而 fail。
        """
        steps = 3
        svc = self._make_service(steps=steps)
        # 规则间隔 60 秒，可以被 infer_freq 识别为 "min"
        data = [{"timestamp": 1700000000 + i * 60, "value": float(i)} for i in range(5)]
        config = {"steps": steps}
        response = await svc.predict(data, config)
        assert response.success is True
        assert response.prediction is not None
        assert len(response.prediction) == steps

    @pytest.mark.asyncio
    async def test_predict_metadata_steps_matches_config(self):
        """metadata.prediction_steps 应等于请求中的 steps。"""
        steps = 5
        svc = self._make_service(steps=steps)
        data = [{"timestamp": 1700000000 + i * 60, "value": float(i)} for i in range(4)]
        config = {"steps": steps}
        response = await svc.predict(data, config)
        assert response.metadata.prediction_steps == steps

    @pytest.mark.asyncio
    async def test_predict_invalid_schema_returns_error_response(self):
        """格式错误（缺少 steps）应返回 success=False 而非抛出异常。

        Revert 验证：若移除 try/except 校验块，此 test 将因未捕获异常而 fail。
        """
        svc = self._make_service()
        data = [{"timestamp": 1700000000 + i * 60, "value": float(i)} for i in range(3)]
        # config 缺少必填的 steps
        config = {}
        response = await svc.predict(data, config)
        assert response.success is False
        assert response.error is not None
        assert response.error.code == "E1000"

    @pytest.mark.asyncio
    async def test_predict_history_length_in_metadata(self):
        """metadata.input_data_points 等于请求数据点数。"""
        svc = self._make_service(steps=2)
        data = [{"timestamp": 1700000000 + i * 60, "value": 1.0} for i in range(6)]
        config = {"steps": 2}
        response = await svc.predict(data, config)
        assert response.metadata.input_data_points == 6
