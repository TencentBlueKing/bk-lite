"""BentoML service definition."""

import bentoml
from loguru import logger
import time
import os

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
        config: dict = None
    ) -> PredictResponse:
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
        
        # 构造 PredictRequest 对象进行验证
        from .schemas import TimeSeriesPoint, DetectionConfig, ResponseMetadata, ErrorDetail, AnomalyPoint
        try:
            data_points = [TimeSeriesPoint(**point) for point in data]
            detect_config = DetectionConfig(**config) if config else None
            request = PredictRequest(data=data_points, config=detect_config)
        except Exception as e:
            logger.error(f"Request validation failed: {e}")
            # 返回验证失败响应
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri if hasattr(self.config, 'mlflow_model_uri') else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=ErrorDetail(
                    code="E1000",
                    message=f"请求格式验证失败: {str(e)}",
                    details={"error_type": type(e).__name__}
                )
            )
        
        logger.info(f"📥 Received anomaly detection request: data_points={len(request.data)}")

        try:
            # 转换为时间序列
            series = request.to_series()
            
            logger.info(f"📊 Input data range: {series.index[0]} to {series.index[-1]}")
            
            # 推断频率（宽松模式，允许不规则序列）
            inferred_freq = None
            try:
                inferred_freq = pd.infer_freq(series.index)
                if inferred_freq:
                    logger.info(f"🕒 Detected frequency: {inferred_freq}")
            except Exception:
                logger.warning("⚠️  Could not infer frequency, treating as irregular time series")
            
            # 执行异常检测
            model_info = f"source={self.config.source}, type={type(self.model).__name__}"
            if self.config.source == "local":
                model_info += f", path={self.config.model_path}"
            elif self.config.source == "mlflow":
                model_info += f", uri={self.config.mlflow_model_uri}"
            
            logger.info(f"🤖 Model info: {model_info}")
            logger.info(f"🔍 Starting anomaly detection...")
            
            detect_start = time.time()
            
            # 准备模型输入（统一字典格式）
            model_input = {'data': series}
            if request.config and request.config.threshold is not None:
                model_input['threshold'] = request.config.threshold
            
            # 调用模型检测（统一接口）
            detection_result = self.model.predict(model_input)
            
            detect_time = time.time() - detect_start
            
            logger.info(f"✅ Detection completed successfully")
            logger.info(f"⏱️  Detection time: {detect_time:.3f}s")
            
            # 解析检测结果
            # 期望格式: {'labels': [0,1,0,...], 'scores': [0.1,0.9,0.2,...], 'probabilities': [0.05,0.95,...]}
            labels = detection_result.get('labels', [])
            scores = detection_result.get('scores', [])
            probabilities = detection_result.get('probabilities', [])
            
            if len(labels) != len(request.data) or len(scores) != len(request.data):
                raise ValueError(
                    f"模型返回结果长度不匹配: 输入{len(request.data)}个点, "
                    f"返回labels={len(labels)}, scores={len(scores)}"
                )
            
            # 兼容性处理：如果模型没有返回probabilities，使用scores作为fallback
            if len(probabilities) != len(request.data):
                logger.warning("模型未返回probabilities，使用scores作为fallback")
                probabilities = scores
            
            # 构造结果点
            result_points = []
            anomaly_count = 0
            for i, point in enumerate(request.data):
                label = int(labels[i])  # 0=正常, 1=异常
                if label == 1:
                    anomaly_count += 1
                    
                result_points.append(AnomalyPoint(
                    timestamp=point.timestamp,
                    value=point.value,
                    label=label,
                    anomaly_score=float(scores[i]),
                    anomaly_probability=float(probabilities[i])
                ))
            
            anomaly_rate = anomaly_count / len(request.data) if len(request.data) > 0 else 0.0
            
            # 构造成功响应
            response = PredictResponse(
                success=True,
                results=result_points,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri if hasattr(self.config, 'mlflow_model_uri') else None,
                    input_data_points=len(request.data),
                    detected_anomalies=anomaly_count,
                    anomaly_rate=anomaly_rate,
                    input_frequency=inferred_freq,
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=None
            )
            
            total_time = time.time() - request_start
            logger.info(f"📈 Detection summary: {anomaly_count}/{len(request.data)} anomalies ({anomaly_rate:.2%})")
            logger.info(f"⏱️  Total request time: {total_time:.3f}s")
            
            prediction_counter.labels(
                model_source=self.config.source,
                status="success",
            ).inc()
            
            return response
            
        except ValueError as e:
            # 验证错误
            logger.error(f"Validation error: {e}")
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri if hasattr(self.config, 'mlflow_model_uri') else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
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
            # 其他错误（模型检测失败等）
            logger.error(f"Detection failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            prediction_counter.labels(
                model_source=self.config.source,
                status="failure",
            ).inc()
            
            return PredictResponse(
                success=False,
                results=None,
                metadata=ResponseMetadata(
                    model_uri=self.config.mlflow_model_uri if hasattr(self.config, 'mlflow_model_uri') else None,
                    input_data_points=len(data) if data else 0,
                    detected_anomalies=0,
                    anomaly_rate=0.0,
                    input_frequency=None,
                    execution_time_ms=(time.time() - request_start) * 1000
                ),
                error=ErrorDetail(
                    code="E2002",
                    message=f"异常检测失败: {str(e)}",
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
