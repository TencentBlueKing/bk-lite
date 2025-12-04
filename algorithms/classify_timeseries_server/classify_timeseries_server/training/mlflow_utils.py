"""MLflow 工具类."""

from typing import Any, Dict, List, Optional
import mlflow
import mlflow.pyfunc
from loguru import logger
import math


class MLFlowUtils:
    """MLflow 工具类，提供可复用的 MLflow 操作."""
    
    @staticmethod
    def setup_experiment(tracking_uri: Optional[str], experiment_name: str):
        """
        设置 MLflow 实验.
        
        Args:
            tracking_uri: MLflow tracking 服务地址，如果为 None 则使用本地文件系统
            experiment_name: 实验名称
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            logger.info(f"MLflow 跟踪地址: {tracking_uri}")
        else:
            mlflow.set_tracking_uri("file:./mlruns")
            logger.info("MLflow 跟踪地址: file:./mlruns")
        
        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow 实验: {experiment_name}")
    
    @staticmethod
    def load_model(model_name: str, model_version: str = "latest"):
        """
        从 MLflow 加载模型.
        
        Args:
            model_name: 模型名称
            model_version: 模型版本，默认为 "latest"
            
        Returns:
            加载的模型对象
        """
        model_uri = f"models:/{model_name}/{model_version}"
        logger.info(f"从以下位置加载模型: {model_uri}")
        return mlflow.pyfunc.load_model(model_uri)
    
    @staticmethod
    def log_params_batch(params: Dict[str, Any]):
        """
        批量记录参数到 MLflow.
        
        Args:
            params: 参数字典
        """
        if params:
            # 过滤掉不支持的参数类型
            valid_params = {}
            for k, v in params.items():
                if isinstance(v, (str, int, float, bool)):
                    valid_params[k] = v
                elif isinstance(v, (list, tuple)):
                    valid_params[k] = str(v)
                else:
                    logger.warning(f"跳过不支持类型 {type(v)} 的参数 {k}")
            
            mlflow.log_params(valid_params)
            logger.debug(f"已记录 {len(valid_params)} 个参数")
    
    @staticmethod
    def log_metrics_batch(
        metrics: Dict[str, float], 
        prefix: str = "", 
        step: Optional[int] = None
    ):
        """
        批量记录指标到 MLflow.
        
        Args:
            metrics: 指标字典
            prefix: 指标名称前缀，如 "train_", "val_", "test_"
            step: 记录步骤（用于时间序列指标）
        """
        if metrics:
            # 过滤有效的指标值
            prefixed_metrics = {}
            for k, v in metrics.items():
                if isinstance(v, (int, float)) and math.isfinite(v):
                    prefixed_metrics[f"{prefix}{k}"] = v
            
            if step is not None:
                for key, value in prefixed_metrics.items():
                    mlflow.log_metric(key, value, step=step)
            else:
                mlflow.log_metrics(prefixed_metrics)
            
            logger.debug(f"已记录 {len(prefixed_metrics)} 个指标 (前缀={prefix})")
    
    @staticmethod
    def log_artifact(local_path: str, artifact_path: Optional[str] = None):
        """
        记录文件到 MLflow.
        
        Args:
            local_path: 本地文件路径
            artifact_path: MLflow 中的artifact路径
        """
        mlflow.log_artifact(local_path, artifact_path)
        logger.debug(f"已记录 artifact: {local_path}")
    
    @staticmethod
    def log_model(
        model: Any,
        artifact_path: str,
        registered_model_name: Optional[str] = None,
        pip_requirements: Optional[List[str]] = None
    ):
        """
        记录模型到 MLflow.
        
        Args:
            model: 模型对象
            artifact_path: artifact 路径
            registered_model_name: 注册的模型名称
            pip_requirements: pip 依赖列表
        """
        mlflow.pyfunc.log_model(
            artifact_path=artifact_path,
            python_model=model,
            registered_model_name=registered_model_name,
            pip_requirements=pip_requirements
        )
        logger.info(f"模型已记录: {registered_model_name or artifact_path}")
