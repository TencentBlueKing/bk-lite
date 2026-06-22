"""异常检测服务 schema 校验和 predict 路径的单元测试。

覆盖：
- TimeSeriesPoint / DetectionConfig / PredictRequest 的 schema 校验
- PredictRequest.to_series() 的排序与去重行为
- DummyModel.predict() 的输入/输出 shape 不变量
- MLService.predict() 的验证失败路径和正常检测路径（使用 DummyModel，无需真实模型）
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 仅加载被测模块，不启动 BentoML 服务（无需真实 BentoML runtime）
# ---------------------------------------------------------------------------

BASE = "classify_anomaly_server.serving"


def _stub_bentoml():
    """向 sys.modules 注入最小化的 bentoml 存根，避免真实 BentoML 启动。"""
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

    # exceptions 子模块（exceptions.py 从这里 import BentoMLException）
    bentoml_exceptions = types.ModuleType("bentoml.exceptions")

    class BentoMLException(Exception):
        error_code = 500

    bentoml_exceptions.BentoMLException = BentoMLException
    bentoml.exceptions = bentoml_exceptions

    # metrics 子模块（metrics.py 从这里 import metrics.Counter / Histogram）
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


_stub_bentoml()


from classify_anomaly_server.serving.schemas.api_schema import (  # noqa: E402
    AnomalyPoint,
    DetectionConfig,
    ErrorDetail,
    PredictRequest,
    PredictResponse,
    ResponseMetadata,
    TimeSeriesPoint,
)
from classify_anomaly_server.serving.models.dummy_model import DummyModel  # noqa: E402


# ---------------------------------------------------------------------------
# Schema 校验测试
# ---------------------------------------------------------------------------


class TestTimeSeriesPointSchema:
    """TimeSeriesPoint 的边界输入校验。"""

    def test_valid_point(self):
        pt = TimeSeriesPoint(timestamp=1700000000, value=42.0)
        assert pt.timestamp == 1700000000
        assert pt.value == 42.0

    def test_missing_timestamp_raises(self):
        with pytest.raises(ValidationError):
            TimeSeriesPoint(value=1.0)

    def test_missing_value_raises(self):
        with pytest.raises(ValidationError):
            TimeSeriesPoint(timestamp=1700000000)


class TestDetectionConfigSchema:
    """DetectionConfig.threshold 的约束校验（gt=0.0）。"""

    def test_valid_threshold(self):
        cfg = DetectionConfig(threshold=0.8)
        assert cfg.threshold == 0.8

    def test_none_threshold_allowed(self):
        cfg = DetectionConfig()
        assert cfg.threshold is None

    def test_zero_threshold_raises(self):
        """threshold=0 不满足 gt=0.0，应抛 ValidationError。"""
        with pytest.raises(ValidationError):
            DetectionConfig(threshold=0.0)

    def test_negative_threshold_raises(self):
        with pytest.raises(ValidationError):
            DetectionConfig(threshold=-0.5)


class TestPredictRequestToSeries:
    """PredictRequest.to_series() 的排序与去重行为。"""

    def _make_request(self, pairs):
        """pairs: list of (timestamp, value)"""
        points = [TimeSeriesPoint(timestamp=t, value=v) for t, v in pairs]
        return PredictRequest(data=points)

    def test_basic_conversion(self):
        req = self._make_request([(1000, 1.0), (2000, 2.0), (3000, 3.0)])
        series = req.to_series()
        assert len(series) == 3
        assert list(series.values) == [1.0, 2.0, 3.0]

    def test_auto_sort_unsorted_timestamps(self):
        """乱序时间戳应被自动升序排列。"""
        req = self._make_request([(3000, 3.0), (1000, 1.0), (2000, 2.0)])
        series = req.to_series()
        assert series.index.is_monotonic_increasing
        assert list(series.values) == [1.0, 2.0, 3.0]

    def test_dedup_keeps_last_value(self):
        """重复时间戳应保留最后一个值。"""
        req = self._make_request([(1000, 1.0), (1000, 99.0), (2000, 2.0)])
        series = req.to_series()
        assert len(series) == 2
        # 1000 对应的值应是最后出现的 99.0
        ts_1000 = pd.to_datetime(1000, unit="s")
        assert series[ts_1000] == 99.0


# ---------------------------------------------------------------------------
# DummyModel 单元测试
# ---------------------------------------------------------------------------


class TestDummyModel:
    """DummyModel.predict() 的输入/输出 shape 不变量。"""

    def setup_method(self):
        self.model = DummyModel()

    def test_output_length_equals_input(self):
        """输出 labels/scores 长度必须等于输入序列长度。"""
        series = pd.Series([1.0, 2.0, 100.0, 1.5, 2.5], index=range(5))
        result = self.model.predict({"data": series})
        assert len(result["labels"]) == 5
        assert len(result["scores"]) == 5

    def test_labels_are_binary(self):
        """labels 仅包含 0 或 1。"""
        series = pd.Series(list(range(10)), dtype=float)
        result = self.model.predict({"data": series})
        assert all(lbl in (0, 1) for lbl in result["labels"])

    def test_scores_in_unit_interval(self):
        """scores 每个值在 [0, 1] 范围内。"""
        series = pd.Series([1.0, 50.0, 1.0, 1.0, 1000.0], dtype=float)
        result = self.model.predict({"data": series})
        assert all(0.0 <= s <= 1.0 for s in result["scores"])

    def test_constant_series_has_no_anomalies(self):
        """所有值相同时，不应检测到异常（std=0 路径）。"""
        series = pd.Series([5.0] * 10)
        result = self.model.predict({"data": series})
        assert all(lbl == 0 for lbl in result["labels"])

    def test_invalid_input_type_raises(self):
        """非 pd.Series 输入应抛 ValueError。"""
        with pytest.raises(ValueError):
            self.model.predict({"data": [1.0, 2.0, 3.0]})

    def test_custom_threshold_affects_labels(self):
        """高阈值应比低阈值产生更少的异常标记。"""
        # 制造一个含明显离群点的序列
        values = [1.0] * 9 + [1000.0]
        series = pd.Series(values, dtype=float)

        result_strict = self.model.predict({"data": series, "threshold": 0.99})
        result_loose = self.model.predict({"data": series, "threshold": 0.1})

        anomalies_strict = sum(result_strict["labels"])
        anomalies_loose = sum(result_loose["labels"])
        assert anomalies_strict <= anomalies_loose


# ---------------------------------------------------------------------------
# MLService.predict() 集成路径测试（使用 DummyModel，不启动真实 BentoML）
# ---------------------------------------------------------------------------


class TestMLServicePredict:
    """在不依赖 MLflow / BentoML runtime 的情况下测试服务推理路径。"""

    def _make_service(self):
        """直接实例化 MLService，注入 DummyModel 和 dummy config。"""
        from classify_anomaly_server.serving.service import MLService

        svc = object.__new__(MLService)
        svc.model = DummyModel()

        # 构造最小 config stub
        config = MagicMock()
        config.source = "dummy"
        config.mlflow_model_uri = None
        svc.config = config
        return svc

    @pytest.mark.asyncio
    async def test_predict_success_returns_correct_shape(self):
        """正常请求：返回 success=True，results 长度等于输入数据点数。"""
        svc = self._make_service()
        data = [{"timestamp": 1700000000 + i, "value": float(i)} for i in range(5)]
        response = await svc.predict(data)
        assert response.success is True
        assert response.results is not None
        assert len(response.results) == 5
        assert response.error is None

    @pytest.mark.asyncio
    async def test_predict_metadata_input_count(self):
        """metadata.input_data_points 等于实际输入点数。"""
        svc = self._make_service()
        data = [{"timestamp": 1700000000 + i, "value": 1.0} for i in range(8)]
        response = await svc.predict(data)
        assert response.metadata.input_data_points == 8

    @pytest.mark.asyncio
    async def test_predict_invalid_schema_returns_error_response(self):
        """格式错误的请求应返回 success=False 而非抛出异常。

        Revert 修复验证：若移除 try/except 块内的 schema 验证逻辑，
        此 test 将抛出未捕获异常而 fail。
        """
        svc = self._make_service()
        # 缺少必填字段 'timestamp'
        data = [{"value": 1.0}]
        response = await svc.predict(data)
        assert response.success is False
        assert response.error is not None
        assert response.error.code == "E1000"

    @pytest.mark.asyncio
    async def test_predict_anomaly_rate_in_unit_interval(self):
        """anomaly_rate 始终在 [0, 1] 范围内。"""
        svc = self._make_service()
        data = [{"timestamp": 1700000000 + i, "value": float(i * 100)} for i in range(6)]
        response = await svc.predict(data)
        assert 0.0 <= response.metadata.anomaly_rate <= 1.0

    @pytest.mark.asyncio
    async def test_predict_with_threshold_config(self):
        """附带 config.threshold 参数不应导致服务报错。"""
        svc = self._make_service()
        data = [{"timestamp": 1700000000 + i, "value": float(i)} for i in range(5)]
        config = {"threshold": 0.9}
        response = await svc.predict(data, config)
        assert response.success is True
