"""时间序列算法基类."""

from abc import ABC, abstractmethod
from typing import Any, Dict
import pandas as pd
import numpy as np


class BaseTimeSeriesAlgorithm(ABC):
    """
    时间序列算法基类.
    
    定义所有算法必须实现的接口，确保可插拔性.
    """
    
    @property
    @abstractmethod
    def algorithm_name(self) -> str:
        """算法名称（用于日志和标识）."""
        pass
    
    @abstractmethod
    def fit(
        self, 
        train_data: pd.Series, 
        hyperparams: Dict[str, Any]
    ) -> Any:
        """
        训练模型.
        
        Args:
            train_data: 训练数据（pd.Series with DatetimeIndex）
            hyperparams: 超参数字典
            
        Returns:
            训练好的模型对象
        """
        pass
    
    @abstractmethod
    def predict(self, model: Any, steps: int) -> np.ndarray:
        """
        预测.
        
        Args:
            model: 训练好的模型
            steps: 预测步数
            
        Returns:
            预测结果数组
        """
        pass
    
    @abstractmethod
    def get_model_wrapper(self, model: Any, freq: str):
        """
        获取 MLflow 部署包装器.
        
        Args:
            model: 训练好的模型
            freq: 时间频率
            
        Returns:
            mlflow.pyfunc.PythonModel 实例
        """
        pass
    
    @abstractmethod
    def get_pip_requirements(self) -> list[str]:
        """
        获取模型依赖包列表.
        
        Returns:
            依赖包列表
        """
        pass
    
    def get_additional_metrics(self, model: Any) -> Dict[str, float]:
        """
        获取算法特定的额外指标（可选实现）.
        
        Args:
            model: 训练好的模型
            
        Returns:
            额外指标字典（如 SARIMA 的 AIC/BIC）
        """
        return {}
    
    def flatten_hyperparams(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        展平超参数用于 MLflow 记录（可选实现）.
        
        Args:
            config: 原始超参数字典
            
        Returns:
            展平后的参数字典
        """
        return config
