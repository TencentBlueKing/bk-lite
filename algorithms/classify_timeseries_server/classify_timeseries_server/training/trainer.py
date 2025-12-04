"""SARIMA 模型训练模块（保留向后兼容）."""

from typing import Dict, Any, Optional
import pandas as pd
from loguru import logger

from .base_model import BaseTimeSeriesModel
from .generic_trainer import TimeSeriesTrainer
from .algorithms.sarima import SARIMAAlgorithm


class SARIMAModel(BaseTimeSeriesModel):
    """
    SARIMA 时间序列模型（保留向后兼容）.
    
    内部委托给新的 TimeSeriesTrainer + SARIMAAlgorithm 实现.
    """
    
    def __init__(self):
        super().__init__()
        self._algorithm = SARIMAAlgorithm()
        self._trainer = TimeSeriesTrainer(self._algorithm)
    
    def build_model(self, train_params: dict):
        """构建 SARIMA 模型."""
        return self._trainer.build_model(train_params)
    
    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        train_config: dict = {},
        mlflow_tracking_uri: Optional[str] = None,
        experiment_name: str = "timeseries_sarima",
        test_size: float = 0.2,
        max_evals: int = 0,
        optimization_metric: str = "rmse",
        **kwargs
    ) -> Dict[str, Any]:
        """
        训练 SARIMA 模型（向后兼容接口）.
        
        Args:
            model_name: 模型名称
            train_dataframe: 训练数据,包含 'date' 和 'value' 列
            val_dataframe: 验证数据（可选，用于超参数优化）
            test_dataframe: 测试数据（可选，如果没有则从训练数据分割）
            train_config: 训练配置，支持固定值或搜索范围定义
            mlflow_tracking_uri: MLflow tracking 地址
            experiment_name: 实验名称
            test_size: 测试集比例
            max_evals: 超参数优化轮次 (0=不优化, >0=优化轮次)
            optimization_metric: 优化目标指标 (rmse/mae/mape)
            **kwargs: 其他参数
            
        Returns:
            训练结果字典
        """
        logger.info("🔄 使用旧版 SARIMAModel 接口 (委托给 TimeSeriesTrainer)")
        
        return self._trainer.train(
            model_name=model_name,
            train_dataframe=train_dataframe,
            val_dataframe=val_dataframe,
            test_dataframe=test_dataframe,
            train_config=train_config,
            mlflow_tracking_uri=mlflow_tracking_uri,
            experiment_name=experiment_name,
            test_size=test_size,
            max_evals=max_evals,
            optimization_metric=optimization_metric,
            **kwargs
        )