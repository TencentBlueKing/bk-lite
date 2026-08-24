"""BentoML service definition."""

import bentoml
from loguru import logger
import time
import os
import sys
import traceback
from pathlib import Path

from .config import get_model_config
from .exceptions import ModelInferenceError
from .metrics import (
    health_check_counter,
    model_load_counter,
    prediction_counter,
    prediction_duration,
)
from .models import load_model
from .schemas import PredictRequest, PredictResponse, PREDICT_MAX_DATA_POINTS

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


@bentoml.service(
    name=f"classify_anomaly_service",
    traffic={"timeout": 30},
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
        logger.info("event=anomaly_service_deployment_setup_completed")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.debug("event=anomaly_service_initializing")
        self.config = get_model_config()
        logger.debug("event=anomaly_service_config_loaded model_source={}", self.config.source)

        try:
            load_start = time.time()
            self.model = load_model(self.config)
            load_time = time.time() - load_start

            model_load_counter.labels(source=self.config.source, status="success").inc()
            logger.info(
                "event=anomaly_model_load_succeeded model_source={} model_type={} duration_ms={:.3f}",
                self.config.source,
                type(self.model).__name__,
                load_time * 1000,
            )

        except Exception as e:
            model_load_counter.labels(source=self.config.source, status="failure").inc()
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=anomaly_model_load_failed failed_stage=model_load error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )

            # 根据环境变量决定是否允许降级到 DummyModel
            allow_fallback = (
                os.getenv("ALLOW_DUMMY_FALLBACK", "false").lower() == "true"
            )

            if allow_fallback:
                from .models.dummy_model import DummyModel

                logger.warning("event=anomaly_model_fallback_enabled fallback=dummy")
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
        logger.info("event=anomaly_service_cleanup_completed")

    @bentoml.api
    async def predict(self, data: list, config: dict = None) -> PredictResponse:
        """
        异常检测接口.

        Args:
            data: 时间序列数据点列表
            config: 检测配置（可选）

        Returns:
            异常检测响应
        """
        import pandas as pd

        request_start = time.time()

        # 快速失败：前置验证（在 try 块外）
        from .schemas import (
            TimeSeriesPoint,
            DetectionConfig,
            ResponseMetadata,
            ErrorDetail,
            AnomalyPoint,
        )

        # 输入上界检查：在展开列表之前拒绝超大请求，防止 OOM
        if not data or len(data) == 0:
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E1000",
                    message="请求数据不能为空",
                    details={"error_type": "ValidationError"},
                ),
            )
        if len(data) > PREDICT_MAX_DATA_POINTS:
            logger.warning(
                "event=anomaly_request_rejected reason=input_too_large data_points={} max_data_points={}",
                len(data),
                PREDICT_MAX_DATA_POINTS,
            )
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=len(data),
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E1002",
                    message=f"数据点数 {len(data)} 超过单次请求上限 {PREDICT_MAX_DATA_POINTS}，请分批提交",
                    details={
                        "error_type": "InputTooLarge",
                        "max_allowed": PREDICT_MAX_DATA_POINTS,
                        "received": len(data),
                    },
                ),
            )

        try:
            data_points = [TimeSeriesPoint(**point) for point in data]
            detect_config = DetectionConfig(**config) if config else None
            request = PredictRequest(data=data_points, config=detect_config)
        except Exception as e:
            logger.warning(
                "event=anomaly_request_rejected reason=invalid_request error_type={}",
                type(e).__name__,
            )
            # 返回验证失败响应
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E1000",
                    message=f"请求格式验证失败: {str(e)}",
                    details={"error_type": type(e).__name__},
                ),
            )

        logger.debug("event=anomaly_request_received data_points={}", len(request.data))

        try:
            # 转换为时间序列
            series = request.to_series()

            logger.debug("event=anomaly_input_ready data_points={}", len(series))

            # 推断频率（宽松模式，允许不规则序列）
            inferred_freq = None
            try:
                inferred_freq = pd.infer_freq(series.index)
                if inferred_freq:
                    logger.debug("event=anomaly_input_frequency_detected frequency={}", inferred_freq)
            except Exception:
                logger.debug("event=anomaly_input_frequency_unknown")

            # 执行异常检测
            logger.debug(
                "event=anomaly_detection_started model_source={} model_type={}",
                self.config.source,
                type(self.model).__name__,
            )

            detect_start = time.time()

            # 准备模型输入（统一字典格式）
            model_input = {"data": series}
            if request.config and request.config.threshold is not None:
                model_input["threshold"] = request.config.threshold

            # 调用模型检测（统一接口）
            detection_result = self.model.predict(model_input)

            detect_time = time.time() - detect_start

            # 解析检测结果
            # 期望格式: {'labels': [0,1,0,...], 'scores': [0.1,0.9,0.2,...], 'anomaly_severity': [0.05,0.95,...]}
            labels = detection_result.get("labels", [])
            scores = detection_result.get("scores", [])
            anomaly_severity = detection_result.get("anomaly_severity", [])

            if len(labels) != len(request.data) or len(scores) != len(request.data):
                raise ValueError(
                    f"模型返回结果长度不匹配: 输入{len(request.data)}个点, "
                    f"返回labels={len(labels)}, scores={len(scores)}"
                )

            # 兼容性处理：如果模型没有返回anomaly_severity，使用scores作为fallback
            if len(anomaly_severity) != len(request.data):
                logger.warning("event=anomaly_severity_fallback fallback=scores")
                anomaly_severity = scores

            # 构造结果点
            result_points = []
            anomaly_count = 0
            for i, point in enumerate(request.data):
                label = int(labels[i])  # 0=正常, 1=异常
                if label == 1:
                    anomaly_count += 1

                result_points.append(
                    AnomalyPoint(
                        timestamp=point.timestamp,
                        value=point.value,
                        label=label,
                        anomaly_score=float(scores[i]),
                        anomaly_severity=float(anomaly_severity[i]),
                    )
                )

            anomaly_rate = (
                anomaly_count / len(request.data) if len(request.data) > 0 else 0.0
            )

            # 构造成功响应
            response = PredictResponse(
                success=True,
                results=result_points,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=len(request.data),
                    detected_anomalies=anomaly_count,
                    anomaly_rate=anomaly_rate,
                    input_frequency=inferred_freq,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=None,
            )

            total_time = time.time() - request_start
            logger.info(
                "event=anomaly_detection_completed model_source={} data_points={} anomalies={} "
                "anomaly_rate={:.4f} detect_duration_ms={:.3f} total_duration_ms={:.3f}",
                self.config.source,
                len(request.data),
                anomaly_count,
                anomaly_rate,
                detect_time * 1000,
                total_time * 1000,
            )

            prediction_counter.labels(
                model_source=self.config.source,
                status="success",
            ).inc()

            return response

        except ValueError as e:
            # 验证错误
            logger.warning(
                "event=anomaly_detection_failed failed_stage=result_validation error_type={}",
                type(e).__name__,
            )
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E1001",
                    message=str(e),
                    details={"error_type": "ValidationError"},
                ),
            )

        except Exception as e:
            # 其他错误（模型检测失败等）
            logger.opt(exception=_safe_exception_info(e)).error(
                "event=anomaly_detection_failed failed_stage=model_predict error_type={} call_chain={}",
                type(e).__name__,
                _safe_exception_call_chain(e),
            )

            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()

            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri
                    if hasattr(self.config, "mlflow_model_uri")
                    else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000,
                ),
                error=ErrorDetail(
                    code="E2002",
                    message=f"异常检测失败: {str(e)}",
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
