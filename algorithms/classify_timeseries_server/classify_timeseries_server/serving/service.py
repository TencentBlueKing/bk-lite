"""BentoML service definition."""

import bentoml
from loguru import logger

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

        try:
            self.model = load_model(self.config)
            model_load_counter.labels(
                source=self.config.source, status="success").inc()
            logger.info("Model loaded successfully")
        except Exception as e:
            model_load_counter.labels(
                source=self.config.source, status="failure").inc()
            logger.error(f"Failed to load model: {e}")
            raise

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
    async def predict(self, request: PredictRequest) -> PredictResponse:
        """
        预测接口.

        Args:
            request: 预测请求

        Returns:
            预测响应

        Raises:
            ModelInferenceError: 模型推理失败
        """
        logger.info(f"Received prediction request: {request.features}")

        try:
            with prediction_duration.labels(model_source=self.config.source).time():
                # 调用模型预测
                if hasattr(self.model, "predict"):
                    # Dummy model or sklearn-like interface
                    prediction = self.model.predict(request.features)
                else:
                    # MLflow pyfunc interface
                    import pandas as pd

                    df = pd.DataFrame([request.features])
                    prediction = self.model.predict(df)[0]

                # 构造响应
                response = PredictResponse(
                    prediction=float(prediction),
                    model_version=getattr(self.model, "version", "unknown"),
                    source=self.config.source,
                )

            prediction_counter.labels(
                model_source=self.config.source,
                status="success",
            ).inc()
            logger.info(f"Prediction successful: {response.prediction}")
            return response

        except Exception as e:
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            logger.error(f"Prediction failed: {e}")
            raise ModelInferenceError(
                f"Model inference failed: {str(e)}") from e

    @bentoml.api
    async def health(self) -> dict:
        """健康检查接口."""
        health_check_counter.inc()
        return {
            "status": "healthy",
            "model_source": self.config.source,
            "model_version": getattr(self.model, "version", "unknown"),
        }
