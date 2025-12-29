"""BentoML service definition."""

import bentoml
from loguru import logger
import mlflow
import os
import time

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
from .schemas import PredictRequest, PredictResponse


@bentoml.service(
    name=f"{{project_name}}_service",
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
        logger.info("=== Deployment setup started ===")
        # 可以在这里做全局初始化,例如:
        # - 预热模型缓存
        # - 下载共享资源
        # - 初始化全局连接池
        logger.info("=== Deployment setup completed ===")

    def __init__(self) -> None:
        """初始化服务,加载配置和模型."""
        logger.info("Service instance initializing...")
        self.config = get_model_config()
        logger.info(f"Config loaded: {self.config}")

        # 启动时验证配置（快速失败）
        self._validate_config()

        # 尝试加载模型
        try:
            load_start = time.time()
            self.model = load_model(self.config)
            load_time = time.time() - load_start
            
            model_load_counter.labels(
                source=self.config.source, status="success").inc()
            logger.info(f"⏱️  Model loaded successfully in {load_time:.3f}s: {self.config.mlflow_model_uri or 'local/dummy'}")
            
        except Exception as e:
            model_load_counter.labels(
                source=self.config.source, status="failure").inc()
            logger.error(f"❌ Failed to load model: {e}", exc_info=True)
            
            # 根据环境变量决定是否允许降级到 DummyModel
            allow_fallback = os.getenv("ALLOW_DUMMY_FALLBACK", "false").lower() == "true"
            
            if allow_fallback:
                from .models.dummy_model import DummyModel
                logger.warning("⚠️  ALLOW_DUMMY_FALLBACK=true, using DummyModel as fallback")
                self.model = DummyModel()
                model_load_counter.labels(
                    source="dummy_fallback", status="success").inc()
            else:
                logger.error(
                    "Model loading failed and fallback is disabled. "
                    "Set ALLOW_DUMMY_FALLBACK=true to enable DummyModel fallback."
                )
                raise RuntimeError(
                    f"Failed to load model from source '{self.config.source}'. "
                    "Service cannot start without a valid model. "
                    "Enable fallback with ALLOW_DUMMY_FALLBACK=true for development/testing."
                ) from e
    
    def _validate_config(self) -> None:
        """验证模型配置（启动时快速检查）."""
        from pathlib import Path
        
        logger.info("Validating model configuration...")
        
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
            
            logger.info(f"✅ Local model config validated: {model_path}")
        
        elif self.config.source == "mlflow":
            # MLflow Registry 模式：检查 URI
            if not self.config.mlflow_model_uri:
                raise ValueError(
                    "MODEL_SOURCE is 'mlflow' but MLFLOW_MODEL_URI is not set. "
                    "Example: models:/model_name/version or models:/model_name/Production"
                )
            
            logger.info(f"✅ MLflow model config validated: {self.config.mlflow_model_uri}")
        
        elif self.config.source == "dummy":
            logger.info("✅ Using dummy model (no validation needed)")
        
        else:
            logger.warning(f"⚠️  Unknown model source: {self.config.source}, will attempt to load")

    @bentoml.on_shutdown
    def cleanup(self) -> None:
        """
        服务关闭时的清理操作.

        用于释放资源、关闭连接等.
        """
        logger.info("=== Service shutdown: cleaning up resources ===")
        # 清理逻辑,例如:
        # - 关闭数据库连接
        # - 保存缓存状态
        # - 释放 GPU 显存
        logger.info("=== Cleanup completed ===")

    @bentoml.api
    async def predict(
        self,
        data: list,
        config: dict
    ) -> PredictResponse:
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
        
        # 构造 PredictRequest 对象进行验证
        from .schemas import TimeSeriesPoint, PredictionConfig, ResponseMetadata, ErrorDetail
        try:
            data_points = [TimeSeriesPoint(**point) for point in data]
            pred_config = PredictionConfig(**config)
            request = PredictRequest(data=data_points, config=pred_config)
        except Exception as e:
            logger.error(f"Request validation failed: {e}")
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
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=ErrorDetail(
                    code="E1000",
                    message=f"请求格式验证失败: {str(e)}",
                    details={"error_type": type(e).__name__}
                )
            )
        
        logger.info(f"Received prediction request: steps={request.config.steps}, data_points={len(request.data)}")

        try:
            # 转换历史数据
            history = request.to_series()
            steps = request.config.steps
            
            # 推断频率（严格验证）
            inferred_freq = pd.infer_freq(history.index)
            if inferred_freq is None:
                raise ValueError("无法推断输入数据的时间频率，请检查时间戳是否规则")
            
            logger.info(f"Detected frequency: {inferred_freq}")
            
            # 执行预测（添加模型来源信息）
            model_info = f"source={self.config.source}, type={type(self.model).__name__}"
            if self.config.source == "local":
                model_info += f", path={self.config.model_path}"
            elif self.config.source == "mlflow":
                model_info += f", uri={self.config.mlflow_model_uri}"
            
            logger.info(f"🔮 Executing prediction with model [{model_info}]")
            
            # 根据阈值决定预测模式
            threshold = request.config.threshold
            if threshold and steps > threshold:
                logger.info(f"预测步数({steps})超过阈值({threshold}), 使用滚动预测模式")
                predict_mode = 'rolling'
            else:
                predict_mode = 'recursive'
                if threshold and steps > threshold * 0.8:
                    logger.warning(f"预测步数({steps})接近阈值({threshold}), 建议使用滚动预测")
            
            predict_start = time.time()
            prediction_values = self.model.predict({
                'history': history,
                'steps': steps,
                'mode': predict_mode,
                'threshold': threshold
            })
            predict_time = time.time() - predict_start
            logger.info(f"⏱️  Prediction executed in {predict_time:.3f}s (mode={predict_mode})")
            
            # 生成预测时间戳
            last_timestamp = history.index[-1]
            predicted_points = []
            for i in range(1, steps + 1):
                next_ts = last_timestamp + i * pd.tseries.frequencies.to_offset(inferred_freq)
                predicted_points.append(TimeSeriesPoint(
                    timestamp=next_ts.isoformat(),
                    value=float(prediction_values[i-1])
                ))
            
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
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=None
            )
            
            total_time = time.time() - request_start
            logger.info(f"⏱️  Total request time: {total_time:.3f}s")
            
            return response
            
        except ValueError as e:
            # 验证错误（频率推断失败等）
            logger.error(f"Validation error: {e}")
            return PredictResponse(
                success=False,
                history=None,
                prediction=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=0,
                    input_data_points=len(data) if data else 0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=ErrorDetail(
                    code="E1001",
                    message=str(e),
                    details={"error_type": "ValidationError"}
                )
            )
            
        except Exception as e:
            # 其他错误（模型预测失败等）
            logger.error(f"Prediction failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return PredictResponse(
                success=False,
                history=None,
                prediction=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri,
                    prediction_steps=0,
                    input_data_points=len(data) if data else 0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=ErrorDetail(
                    code="E2002",
                    message=f"模型预测失败: {str(e)}",
                    details={"error_type": type(e).__name__}
                )
            )

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
