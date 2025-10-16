from typing import Any, Dict, List, Optional, Tuple
import mlflow
import mlflow.sklearn
from loguru import logger


class MLFlowUtils:
    """MLflow 工具类，提供可复用的 MLflow 操作"""
    
    @staticmethod
    def setup_experiment(tracking_uri: str, experiment_name: str):
        """设置 MLflow 实验
        
        Args:
            tracking_uri: MLflow tracking 服务地址，如果为 None 则使用本地文件系统
            experiment_name: 实验名称
        """
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        else:
            mlflow.set_tracking_uri("file:./mlruns")
        mlflow.set_experiment(experiment_name)
    
    @staticmethod
    def load_model(model_name: str, model_version: str = "latest"):
        """从 MLflow 加载模型
        
        Args:
            model_name: 模型名称
            model_version: 模型版本，默认为 "latest"
            
        Returns:
            加载的模型对象
        """
        model_uri = f"models:/{model_name}/{model_version}"
        return mlflow.sklearn.load_model(model_uri)
    
    @staticmethod
    def log_params_batch(params: Dict[str, Any]):
        """批量记录参数到 MLflow
        
        Args:
            params: 参数字典
        """
        if params:
            mlflow.log_params(params)
            logger.debug(f"已记录 {len(params)} 个参数")
    
    @staticmethod
    def log_metrics_batch(metrics: Dict[str, float], prefix: str = "", step: Optional[int] = None):
        """批量记录指标到 MLflow
        
        Args:
            metrics: 指标字典
            prefix: 指标名称前缀，如 "train_", "val_", "test_"
            step: 记录步骤（用于时间序列指标）
        """
        if metrics:
            prefixed_metrics = {f"{prefix}{k}": v for k, v in metrics.items()}
            if step is not None:
                for key, value in prefixed_metrics.items():
                    mlflow.log_metric(key, value, step=step)
            else:
                mlflow.log_metrics(prefixed_metrics)
            logger.debug(f"已记录 {len(metrics)} 个指标 (prefix={prefix})")
    
    @staticmethod
    def log_training_history(
        train_scores: List[float],
        val_scores: List[float],
        metric_name: str,
        additional_metrics: Optional[Dict[str, List[float]]] = None
    ):
        """记录训练历史到 MLflow
        
        Args:
            train_scores: 训练集分数列表
            val_scores: 验证集分数列表
            metric_name: 指标名称，如 "f1", "accuracy"
            additional_metrics: 其他指标字典，如 {"overfitting": [...]}
        """
        for i, (train_score, val_score) in enumerate(zip(train_scores, val_scores), 1):
            mlflow.log_metric(f"train_{metric_name}", train_score, step=i)
            mlflow.log_metric(f"val_{metric_name}", val_score, step=i)
            
            # 记录过拟合程度
            overfitting = train_score - val_score
            mlflow.log_metric("overfitting", overfitting, step=i)
        
        # 记录其他指标
        if additional_metrics:
            for metric_key, metric_values in additional_metrics.items():
                for i, value in enumerate(metric_values, 1):
                    mlflow.log_metric(metric_key, value, step=i)
        
        logger.info(f"已记录 {len(train_scores)} 步的训练历史")
    
    @staticmethod
    def log_model_sklearn(
        model: Any,
        registered_model_name: str,
        artifact_path: str = "model"
    ) -> str:
        """记录 sklearn 模型到 MLflow
        
        Args:
            model: sklearn 模型对象
            registered_model_name: 注册模型的名称
            artifact_path: 模型存储路径
            
        Returns:
            模型 URI
        """
        model_info = mlflow.sklearn.log_model(
            sk_model=model,
            artifact_path=artifact_path,
            registered_model_name=registered_model_name
        )
        logger.info(f"模型已注册: {registered_model_name}")
        return model_info.model_uri
    
    @staticmethod
    def get_latest_model_version(model_name: str) -> Optional[str]:
        """获取模型的最新版本号
        
        Args:
            model_name: 模型名称
            
        Returns:
            最新版本号，如果模型不存在返回 None
        """
        try:
            client = mlflow.tracking.MlflowClient()
            latest_versions = client.get_latest_versions(model_name, stages=["None", "Production", "Staging"])
            if latest_versions:
                versions = [int(v.version) for v in latest_versions]
                return str(max(versions))
            return None
        except Exception as e:
            logger.warning(f"获取模型最新版本失败: {e}")
            return None
    
    @staticmethod
    def log_training_results(
        params: Dict[str, Any],
        train_scores: List[float],
        val_scores: List[float],
        metric_name: str,
        val_metrics: Optional[Dict[str, float]] = None,
        test_metrics: Optional[Dict[str, float]] = None,
        model: Optional[Any] = None,
        model_name: Optional[str] = None
    ):
        """一站式记录训练结果到 MLflow
        
        这是一个便捷方法，集成了参数、训练历史、评估指标和模型的记录。
        
        Args:
            params: 超参数字典
            train_scores: 训练集分数历史
            val_scores: 验证集分数历史
            metric_name: 主要指标名称
            val_metrics: 验证集最终指标
            test_metrics: 测试集最终指标
            model: 训练好的模型（可选）
            model_name: 模型注册名称（可选，需要与 model 一起使用）
        """
        with mlflow.start_run():
            # 记录参数
            MLFlowUtils.log_params_batch(params)
            
            # 记录训练历史
            MLFlowUtils.log_training_history(train_scores, val_scores, metric_name)
            
            # 记录最终指标
            if val_metrics:
                MLFlowUtils.log_metrics_batch(val_metrics, prefix="val_")
            if test_metrics:
                MLFlowUtils.log_metrics_batch(test_metrics, prefix="test_")
            
            # 记录模型
            if model is not None and model_name is not None:
                MLFlowUtils.log_model_sklearn(model, model_name)
            
            logger.info("训练结果已完整记录到 MLflow")
