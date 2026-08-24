"""BentoML service definition."""

import bentoml
from loguru import logger
import mlflow
import os
import sys
import time
import traceback
from pathlib import Path

import mlflow.sklearn

from .config import get_model_config
from .exceptions import ModelInferenceError
from .metrics import (
    health_check_counter,
    model_load_counter,
    prediction_counter,
    prediction_duration,
)
from .models import load_model
from .prediction_budget import (
    RecursiveFeatureEngineeringBudgetExceeded,
    enforce_recursive_feature_engineering_budget,
    get_max_recursive_feature_engineering_work,
)
from .schemas.api_schema import MAX_INPUT_DATA_POINTS, MAX_PREDICTION_STEPS, PredictRequest, PredictResponse


MAX_TIMESERIES_PREDICT_TIMEOUT_SECONDS = 290

def _configure_production_logger(sink=sys.stderr) -> None:
    logger.configure(handlers=[{"sink": sink, "diagnose": False, "backtrace": True}])


_configure_production_logger()


def _safe_exception_call_chain(error: BaseException, max_frames: int = 12) -> str:
    frames = traceback.extract_tb(error.__traceback__)
    return ">".join(f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in frames[-max_frames:]) or "-"


class _SafeLogException(RuntimeError):
    pass


def _safe_exception_info(error: BaseException):
    safe_error = _SafeLogException(type(error).__name__)
    return _SafeLogException, safe_error, error.__traceback__


def get_timeseries_predict_timeout_seconds() -> int:
    raw_timeout = os.getenv("TIMESERIES_PREDICT_TIMEOUT_SECONDS", "120")
    try:
        timeout = int(raw_timeout)
    except ValueError:
        raise ValueError("TIMESERIES_PREDICT_TIMEOUT_SECONDS must be an integer between 1 and 290") from None
    if not 1 <= timeout <= MAX_TIMESERIES_PREDICT_TIMEOUT_SECONDS:
        raise ValueError("TIMESERIES_PREDICT_TIMEOUT_SECONDS must be an integer between 1 and 290")
    return timeout


TIMESERIES_PREDICT_TIMEOUT_SECONDS = get_timeseries_predict_timeout_seconds()
MAX_RECURSIVE_FEATURE_ENGINEERING_WORK = (
    get_max_recursive_feature_engineering_work()
)


@bentoml.service(
    name="classify_timeseries_service",
    traffic={"timeout": TIMESERIES_PREDICT_TIMEOUT_SECONDS},
)
class MLService:
    """机器学习模型服务."""

    @bentoml.on_deployment
    def setup() -> None:
        """
        部署时执行一次的全局初始化.

        用于预热缓存、下载资源等全局操作.
        不接收 self 参数,类似静态方法.
        """
        # 可以在这里做全局初始化,例如:
        # - 预热模型缓存
        # - 下载共享资源
        # - 初始化全局连接池
        logger.info("event=timeseries_deployment_setup_completed")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.debug("event=timeseries_service_initializing")
        self.config = get_model_config()
        logger.debug("event=timeseries_config_loaded model_source={}", self.config.source)

        # 配置验证与模型加载使用同一个显式降级策略：生产默认快速失败，
        # 仅开发/测试明确设置 ALLOW_DUMMY_FALLBACK=true 时降级。
        try:
            self._validate_config()
            load_start = time.time()
            self.model = load_model(self.config)
            load_time = time.time() - load_start

            model_load_counter.labels(source=self.config.source, status="success").inc()
            logger.info(
                "event=timeseries_model_load_succeeded model_source={} model_type={} duration_ms={:.3f}",
                self.config.source,
                type(self.model).__name__,
                load_time * 1000,
            )

        except Exception as e:
            model_load_counter.labels(source=self.config.source, status="failure").inc()
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=timeseries_model_load_failed failed_stage=model_load error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )

            # 根据环境变量决定是否允许降级到 DummyModel
            allow_fallback = (
                os.getenv("ALLOW_DUMMY_FALLBACK", "false").lower() == "true"
            )

            if allow_fallback:
                from .models.dummy_model import DummyModel

                logger.warning("event=timeseries_model_fallback_enabled fallback=dummy")
                self.model = DummyModel()
                model_load_counter.labels(
                    source="dummy_fallback", status="success"
                ).inc()
            else:
                raise RuntimeError(
                    f"Failed to load model from source '{self.config.source}'. "
                    "Service cannot start without a valid model. "
                    "Enable fallback with ALLOW_DUMMY_FALLBACK=true for development/testing."
                ) from e

    def _validate_config(self) -> None:
        """验证模型配置（启动时快速检查）."""
        from pathlib import Path

        logger.debug("event=timeseries_model_config_validation_started")

        if self.config.source == "local":
            # 本地模式：检查路径和关键文件
            if not self.config.model_path:
                raise ValueError(
                    "MODEL_SOURCE is 'local' but MODEL_PATH is not set. "
                    "Please set MODEL_PATH environment variable to a valid MLflow model directory."
                )

            model_path = Path(self.config.model_path)

            if not model_path.exists():
                raise ValueError(
                    f"MODEL_PATH does not exist: {model_path}. "
                    "Ensure the path is correct and accessible."
                )

            if not model_path.is_dir():
                raise ValueError(
                    f"MODEL_PATH must be a directory (MLflow model format), got: {model_path}. "
                    "Example: /path/to/mlruns/1/<run_id>/artifacts/model/"
                )

            if not (model_path / "MLmodel").exists():
                raise ValueError(
                    f"Invalid MLflow model at {model_path}: MLmodel file not found. "
                    "Ensure the path points to a valid MLflow model directory containing MLmodel file."
                )

            logger.info("event=timeseries_model_config_validated model_source=local")

        elif self.config.source == "mlflow":
            # MLflow Registry 模式：检查 URI
            if not self.config.mlflow_model_uri:
                raise ValueError(
                    "MODEL_SOURCE is 'mlflow' but MLFLOW_MODEL_URI is not set. "
                    "Example: models:/model_name/version or models:/model_name/Production"
                )

            logger.info("event=timeseries_model_config_validated model_source=mlflow")

        elif self.config.source == "dummy":
            logger.info("event=timeseries_model_config_validated model_source=dummy")

        else:
            logger.warning(
                "event=timeseries_model_source_unknown model_source={}",
                self.config.source,
            )

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        # 清理逻辑,例如:
        # - 关闭数据库连接
        # - 保存缓存状态
        # - 释放 GPU 显存
        logger.info("event=timeseries_cleanup_completed")

    @bentoml.api
    async def predict(self, data: list, config: dict) -> PredictResponse:
        """
        预测接口.

        Args:
            data: 历史时间序列数据点列表
            config: 预测配置（包含 steps）

        Returns:
            预测响应
        """
        import time
        import pandas as pd

        request_start = time.time()

        # 快速失败：前置验证（在 try 块外）
        from .schemas import (
            TimeSeriesPoint,
            PredictionConfig,
            ResponseMetadata,
            ErrorDetail,
        )

        try:
            data_points = [TimeSeriesPoint(**point) for point in data]
            pred_config = PredictionConfig(**config)
            request = PredictRequest(data=data_points, config=pred_config)
        except Exception as e:
            logger.warning(
                "event=timeseries_request_rejected reason=invalid_request error_type={}",
                type(e).__name__,
            )
            # 返回验证失败响应
            return PredictResponse(
                success=False,
                history=None,
                prediction=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=0,
                    input_data_points=len(data) if data else 0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E1000",
                    message=f"请求格式验证失败: {str(e)}",
                    details={"error_type": type(e).__name__},
                ),
            )

        logger.debug(
            "event=timeseries_request_received steps={} data_points={}",
            request.config.steps,
            len(request.data),
        )

        try:
            # 转换历史数据
            history = request.to_series()
            # 服务层硬截断：即使 schema 校验被绕过也不会触发无界循环
            steps = min(request.config.steps, MAX_PREDICTION_STEPS)
            if len(request.data) > MAX_INPUT_DATA_POINTS:
                raise ValueError(
                    f"输入数据点数 {len(request.data)} 超过上限 {MAX_INPUT_DATA_POINTS}"
                )

            logger.debug("event=timeseries_input_ready data_points={}", len(history))

            # 推断频率（严格验证）
            inferred_freq = pd.infer_freq(history.index)
            if inferred_freq is None:
                raise ValueError("无法推断输入数据的时间频率，请检查时间戳是否规则")

            logger.debug("event=timeseries_input_frequency_detected frequency={}", inferred_freq)

            # 执行预测（添加模型来源信息）
            logger.debug(
                "event=timeseries_prediction_started model_source={} model_type={} steps={}",
                self.config.source,
                type(self.model).__name__,
                steps,
            )

            enforce_recursive_feature_engineering_budget(
                self.model,
                history_points=len(history),
                steps=steps,
                limit=MAX_RECURSIVE_FEATURE_ENGINEERING_WORK,
            )

            predict_start = time.time()
            prediction_values = self.model.predict({"history": history, "steps": steps})
            predict_time = time.time() - predict_start

            logger.debug(
                "event=timeseries_model_predict_completed predictions={} duration_ms={:.3f}",
                len(prediction_values),
                predict_time * 1000,
            )

            # 生成预测时间戳
            last_timestamp = history.index[-1]
            predicted_points = []
            for i in range(1, steps + 1):
                next_ts = last_timestamp + i * pd.tseries.frequencies.to_offset(
                    inferred_freq
                )
                # 转换为Unix时间戳（秒级）
                timestamp_unix = int(next_ts.timestamp())
                predicted_points.append(
                    TimeSeriesPoint(
                        timestamp=timestamp_unix, value=float(prediction_values[i - 1])
                    )
                )

            # 构造成功响应
            response = PredictResponse(
                success=True,
                history=request.data,
                prediction=predicted_points,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=steps,
                    input_data_points=len(request.data),
                    input_frequency=inferred_freq,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=None,
            )

            total_time = time.time() - request_start
            logger.info(
                "event=timeseries_prediction_completed model_source={} input_points={} prediction_points={} "
                "duration_ms={:.3f}",
                self.config.source,
                len(request.data),
                len(predicted_points),
                total_time * 1000,
            )

            return response

        except ValueError as e:
            # 验证错误（频率推断失败等）
            logger.warning(
                "event=timeseries_prediction_failed failed_stage=result_validation error_type={}",
                type(e).__name__,
            )
            return PredictResponse(
                success=False,
                history=None,
                prediction=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=0,
                    input_data_points=len(data) if data else 0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code=(
                        "E1002"
                        if isinstance(
                            e, RecursiveFeatureEngineeringBudgetExceeded
                        )
                        else "E1001"
                    ),
                    message=str(e),
                    details=(
                        {
                            "error_type": type(e).__name__,
                            "history_points": e.history_points,
                            "steps": e.steps,
                            "estimated_work": e.estimated_work,
                            "limit": e.limit,
                        }
                        if isinstance(
                            e, RecursiveFeatureEngineeringBudgetExceeded
                        )
                        else {"error_type": "ValidationError"}
                    ),
                ),
            )

        except Exception as e:
            # 其他错误（模型预测失败等）
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=timeseries_prediction_failed failed_stage=model_predict error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )
            return PredictResponse(
                success=False,
                history=None,
                prediction=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=0,
                    input_data_points=len(data) if data else 0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E2002",
                    message=f"模型预测失败: {str(e)}",
                    details={"error_type": type(e).__name__},
                ),
            )

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "startup_instance_id": os.getenv("SERVING_INSTANCE_ID", ""),
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
