"""日志聚类服务 schema 校验、SpellModel 推理行为和 predict 路径的单元测试。

覆盖：
- LogClusterRequest / LogClusterConfig 的 schema 校验（含边界值）
- SpellModel.fit() → predict() 的基础行为不变量（无需 MLflow）
- MLService.predict() 的聚合响应结构（使用 SpellModel 作模型，不启动真实 BentoML）
"""

import sys
import types
from unittest.mock import MagicMock, patch  # noqa: F401

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# 最小化 BentoML 存根
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


# mlflow stub（spell_model.py 在 fit() 中条件引用 mlflow，trainer.py 也引用多个子模块）
def _stub_mlflow():
    mlflow = types.ModuleType("mlflow")
    mlflow.active_run = lambda: None  # 无活跃 run，跳过 MLflow 记录
    mlflow.log_param = lambda *a, **kw: None
    mlflow.log_metric = lambda *a, **kw: None
    mlflow.log_params = lambda *a, **kw: None
    mlflow.log_metrics = lambda *a, **kw: None
    mlflow.set_tracking_uri = lambda *a, **kw: None
    mlflow.set_experiment = lambda *a, **kw: None

    for submod in ["pyfunc", "sklearn", "xgboost", "pytorch", "tensorflow",
                   "lightgbm", "catboost", "spacy", "entities", "tracking",
                   "client", "MlflowClient"]:
        sub = types.ModuleType(f"mlflow.{submod}")
        setattr(mlflow, submod, sub)
        sys.modules.setdefault(f"mlflow.{submod}", sub)

    sys.modules.setdefault("mlflow", mlflow)


_stub_bentoml()
_stub_mlflow()


from classify_log_server.serving.schemas.api_schema import (  # noqa: E402
    LogClusterConfig,
    LogClusterRequest,
)
from classify_log_server.training.models.spell_model import SpellModel  # noqa: E402


# ---------------------------------------------------------------------------
# Schema 校验测试
# ---------------------------------------------------------------------------


class TestLogClusterConfigSchema:
    """LogClusterConfig 参数约束校验。"""

    def test_defaults(self):
        cfg = LogClusterConfig()
        assert cfg.max_samples == 5
        assert cfg.sort_by == "count"
        assert cfg.return_details is False

    def test_valid_max_samples(self):
        cfg = LogClusterConfig(max_samples=1)
        assert cfg.max_samples == 1
        cfg2 = LogClusterConfig(max_samples=20)
        assert cfg2.max_samples == 20

    def test_max_samples_too_low_raises(self):
        with pytest.raises(ValidationError):
            LogClusterConfig(max_samples=0)

    def test_max_samples_too_high_raises(self):
        with pytest.raises(ValidationError):
            LogClusterConfig(max_samples=21)

    def test_invalid_sort_by_raises(self):
        with pytest.raises(ValidationError):
            LogClusterConfig(sort_by="name")

    def test_valid_sort_by_cluster_id(self):
        cfg = LogClusterConfig(sort_by="cluster_id")
        assert cfg.sort_by == "cluster_id"


class TestLogClusterRequestSchema:
    """LogClusterRequest.data 边界校验。"""

    def test_valid_single_log(self):
        req = LogClusterRequest(data=["User login failed"])
        assert len(req.data) == 1

    def test_empty_data_raises(self):
        with pytest.raises(ValidationError):
            LogClusterRequest(data=[])

    def test_oversized_log_raises(self):
        """单条日志超过 10 KB 应被 field_validator 拒绝。"""
        huge_log = "A" * (10 * 1024 + 1)
        with pytest.raises(ValidationError):
            LogClusterRequest(data=[huge_log])

    def test_config_uses_defaults_when_omitted(self):
        req = LogClusterRequest(data=["some log"])
        assert req.config.max_samples == 5


# ---------------------------------------------------------------------------
# SpellModel 行为不变量测试
# ---------------------------------------------------------------------------


class TestSpellModel:
    """SpellModel.fit() → predict() 的核心不变量（不依赖 MLflow/BentoML）。"""

    LOG_SAMPLES = [
        "User login failed from IP 192.168.1.100",
        "User login failed from IP 10.0.0.5",
        "Database connection timeout after 30 seconds",
        "Database connection timeout after 60 seconds",
        "Service started successfully on port 8080",
    ]

    def _fit_model(self):
        model = SpellModel(tau=0.4, min_cluster_size=1)
        model.fit(self.LOG_SAMPLES, log_to_mlflow=False, verbose=False)
        return model

    def test_fit_creates_at_least_one_cluster(self):
        model = self._fit_model()
        assert len(model.clusters) >= 1

    def test_predict_output_length_equals_input(self):
        """predict() 输出长度必须等于输入日志条数（核心 shape 不变量）。

        Revert 验证：若移除 predict() 的 cluster_ids.append 逻辑，
        输出长度会不匹配，本 test 将 fail。
        """
        model = self._fit_model()
        logs = ["User login failed from IP 1.2.3.4", "Unknown event occurred"]
        result = model.predict(logs)
        assert len(result) == len(logs)

    def test_predict_returns_integer_labels(self):
        """每个输出都应是整数（cluster_id 或 -1）。"""
        model = self._fit_model()
        result = model.predict(self.LOG_SAMPLES)
        assert all(isinstance(r, int) for r in result)

    def test_predict_before_fit_raises(self):
        """未训练的模型调用 predict() 应抛 RuntimeError。"""
        model = SpellModel()
        with pytest.raises(RuntimeError):
            model.predict(["any log"])

    def test_similar_logs_map_to_same_cluster(self):
        """结构相似的日志（仅 IP 不同）应被归入同一模板。"""
        model = self._fit_model()
        logs = [
            "User login failed from IP 172.16.0.1",
            "User login failed from IP 172.16.0.2",
        ]
        result = model.predict(logs)
        # 两条结构相同的日志应归入同一 cluster（或均为 unknown=-1，但不应不同）
        assert result[0] == result[1]

    def test_empty_log_returns_unknown(self):
        """空字符串日志应被归入 unknown（cluster_id=-1）。"""
        model = self._fit_model()
        result = model.predict([""])
        assert result[0] == -1


# ---------------------------------------------------------------------------
# MLService.predict() 集成路径测试
# ---------------------------------------------------------------------------


class TestMLServicePredict:
    """测试服务聚合响应结构，使用 mock 模型返回 DataFrame 格式（与服务契约一致）。"""

    def _make_mock_model(self, data, cluster_ids, templates):
        """构造一个 mock model，predict() 返回服务所需的 DataFrame 格式。"""
        import pandas as pd

        def _predict(logs):
            return pd.DataFrame({
                "log": logs,
                "cluster_id": cluster_ids[:len(logs)],
                "template": templates[:len(logs)],
            })

        mock_model = MagicMock()
        mock_model.predict.side_effect = _predict
        return mock_model

    def _make_service(self, mock_model):
        from classify_log_server.serving.service import MLService

        svc = object.__new__(MLService)
        svc.model = mock_model

        config = MagicMock()
        config.source = "dummy"
        svc.config = config
        return svc

    @pytest.mark.asyncio
    async def test_predict_summary_total_logs_matches_input(self):
        """summary.total_logs 必须等于输入日志数。

        Revert 验证：若修改 total_logs = len(data) 逻辑，此 test 将 fail。
        """
        data = [
            "User login failed from IP 1.2.3.4",
            "DB timeout after 10s",
        ]
        mock_model = self._make_mock_model(data, [0, 1], ["User login *", "DB timeout *"])
        svc = self._make_service(mock_model)
        response = await svc.predict(data)
        assert response.summary.total_logs == 2

    @pytest.mark.asyncio
    async def test_predict_coverage_rate_in_unit_interval(self):
        """coverage_rate 必须在 [0, 1] 范围内。"""
        data = [
            "User login failed from IP 5.5.5.5",
            "Unknown brand new event XYZ",
        ]
        # 第二条日志 cluster_id=-1（未匹配）
        mock_model = self._make_mock_model(data, [0, -1], ["User login *", None])
        svc = self._make_service(mock_model)
        response = await svc.predict(data)
        assert 0.0 <= response.summary.coverage_rate <= 1.0

    @pytest.mark.asyncio
    async def test_predict_matched_plus_unknown_equals_total(self):
        """summary.matched_logs + summary.unknown_logs == summary.total_logs。

        此断言守护聚合计数一致性，revert predict 中的计数逻辑即 fail。
        """
        data = [
            "User login failed from IP 1.1.1.1",
            "DB timeout after 30s",
            "Totally unrelated weird stuff abc xyz 123",
        ]
        # 前两条匹配，最后一条未匹配
        mock_model = self._make_mock_model(
            data, [0, 1, -1], ["User login *", "DB timeout *", None]
        )
        svc = self._make_service(mock_model)
        response = await svc.predict(data)
        assert (
            response.summary.matched_logs + response.summary.unknown_logs
            == response.summary.total_logs
        )

    @pytest.mark.asyncio
    async def test_predict_no_details_by_default(self):
        """默认配置下 details 字段应为 None（按需返回）。"""
        data = ["User login failed from IP 1.2.3.4"]
        mock_model = self._make_mock_model(data, [0], ["User login *"])
        svc = self._make_service(mock_model)
        response = await svc.predict(data)
        assert response.details is None
