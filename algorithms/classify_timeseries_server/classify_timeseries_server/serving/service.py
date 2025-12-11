"""BentoML service definition."""

import bentoml
from loguru import logger
import mlflow
import os

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
    async def predict(
        self,
        model_name: str,
        model_version: int,
        steps: int
    ) -> PredictResponse:
        """
        预测接口.

        Args:
            model_name: 模型名称
            model_version: 模型版本
            steps: 预测步数

        Returns:
            预测响应

        Raises:
            ModelInferenceError: 模型推理失败
        """
        import time
        import pandas as pd
        
        request_start = time.time()
        logger.info(f"Received prediction request: model_name={model_name}, version={model_version}, steps={steps}")

        try:
            # 1. 加载配置
            config_start = time.time()
            config = get_model_config()
            mlflow_tracking_uri = config.mlflow_tracking_uri
            if not mlflow_tracking_uri:
                # raise ModelInferenceError("MLFLOW_TRACKING_URI environment variable not set")
                logger.debug("MLFLOW_TRACKING_URI environment variable not set")
                mlflow_tracking_uri = "http://localhost:15000"
            
            mlflow.set_tracking_uri(mlflow_tracking_uri)
            logger.info(f"⏱️  Config loaded in {time.time() - config_start:.3f}s")
            
            # 2. 加载模型
            model_uri = f"models:/{model_name}/{model_version}"
            logger.info(f"Loading model from: {model_uri}")
            load_start = time.time()
            model = mlflow.pyfunc.load_model(model_uri)
            load_time = time.time() - load_start
            logger.info(f"⏱️  Model loaded in {load_time:.3f}s")

            # 3. 执行预测
            predict_start = time.time()
            prediction = model.predict(pd.DataFrame({
                'steps': [steps]
            }))
            predict_time = time.time() - predict_start
            logger.info(f"⏱️  Prediction executed in {predict_time:.3f}s")
            
            # 4. 构造响应
            response = PredictResponse(
                prediction=prediction.tolist()  # 转换为列表
            )
            
            # 总耗时统计
            total_time = time.time() - request_start
            logger.info(
                f"⏱️  Total request time: {total_time:.3f}s "
                f"(config: {time.time() - config_start:.3f}s, load: {load_time:.3f}s, predict: {predict_time:.3f}s)"
            )
            
            # with prediction_duration.labels(model_source=self.config.source).time():
            #     # 调用模型预测
            #     if hasattr(self.model, "predict"):
            #         # Dummy model or sklearn-like interface
            #         prediction = self.model.predict(request.features)
            #     else:
            #         # MLflow pyfunc interface
            #         import pandas as pd

            #         df = pd.DataFrame([request.features])
            #         prediction = self.model.predict(df)[0]

            #     # 构造响应
            #     response = PredictResponse(
            #         prediction=float(prediction),
            #         model_version=getattr(self.model, "version", "unknown"),
            #         source=self.config.source,
            #     )

            # prediction_counter.labels(
            #     model_source=self.config.source,
            #     status="success",
            # ).inc()
            logger.info(f"Prediction successful: {response}")
            return response

        except Exception as e:
            # prediction_counter.labels(
            #     model_source=self.config.source,
            #     status="failure",
            # ).inc()
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
