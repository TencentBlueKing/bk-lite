"""时间序列模型基类和注册机制"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type
import pandas as pd
import numpy as np
from loguru import logger


class BaseTimeSeriesModel(ABC):
    """时间序列模型基类 - 统一接口
    
    所有时间序列模型必须实现此接口，确保可以被通用训练器调用。
    
    核心方法：
    - fit(): 训练模型
    - predict(): 预测未来N步
    - evaluate(): 评估模型性能
    
    工具方法：
    - get_params(): 获取模型参数
    - save()/load(): 模型持久化
    """
    
    def __init__(self, **kwargs):
        """初始化模型
        
        Args:
            **kwargs: 模型特定的参数
        """
        self.model = None
        self.frequency = None
        self.config = kwargs
        self.is_fitted = False
    
    @abstractmethod
    def fit(self, 
            train_data: pd.Series,
            val_data: Optional[pd.Series] = None,
            **kwargs) -> 'BaseTimeSeriesModel':
        """训练模型
        
        Args:
            train_data: 训练数据（带 DatetimeIndex 的 Series）
            val_data: 验证数据（可选，用于超参数优化）
            **kwargs: 模型特定的训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确
        """
        pass
    
    @abstractmethod
    def predict(self, steps: int) -> np.ndarray:
        """预测未来N步
        
        Args:
            steps: 预测步数
            
        Returns:
            预测结果数组
            
        Raises:
            RuntimeError: 模型未训练
        """
        pass
    
    @abstractmethod
    def evaluate(self, test_data: pd.Series) -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据（带 DatetimeIndex 的 Series）
            
        Returns:
            评估指标字典，至少包含 rmse, mae, mape
            格式: {"rmse": 10.5, "mae": 8.2, "mape": 12.3}
            
        Raises:
            RuntimeError: 模型未训练
        """
        pass
    
    def get_params(self) -> Dict[str, Any]:
        """获取模型参数
        
        Returns:
            模型参数字典
        """
        return self.config.copy()
    
    def save(self, path: str):
        """保存模型到文件
        
        Args:
            path: 保存路径
        """
        import joblib
        if not self.is_fitted:
            logger.warning("保存未训练的模型")
        
        save_data = {
            'model': self.model,
            'frequency': self.frequency,
            'config': self.config,
            'is_fitted': self.is_fitted
        }
        joblib.dump(save_data, path)
        logger.info(f"模型已保存到: {path}")
    
    @classmethod
    def load(cls, path: str) -> 'BaseTimeSeriesModel':
        """从文件加载模型
        
        Args:
            path: 模型文件路径
            
        Returns:
            加载的模型实例
        """
        import joblib
        save_data = joblib.load(path)
        
        instance = cls(**save_data['config'])
        instance.model = save_data['model']
        instance.frequency = save_data['frequency']
        instance.is_fitted = save_data['is_fitted']
        
        logger.info(f"模型已从 {path} 加载")
        return instance
    
    def _check_fitted(self):
        """检查模型是否已训练"""
        if not self.is_fitted:
            raise RuntimeError(
                f"{self.__class__.__name__} 必须先调用 fit() 方法进行训练"
            )
    
    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """计算标准评估指标
        
        Args:
            y_true: 真实值
            y_pred: 预测值
            
        Returns:
            包含 rmse, mae, mape 的字典
        """
        from sklearn.metrics import mean_squared_error, mean_absolute_error
        
        # 确保是 numpy 数组
        y_true = np.asarray(y_true)
        y_pred = np.asarray(y_pred)
        
        # 基础指标
        mse = mean_squared_error(y_true, y_pred)
        rmse = np.sqrt(mse)
        mae = mean_absolute_error(y_true, y_pred)
        
        # MAPE（避免除零）
        mask = y_true != 0
        if mask.sum() > 0:
            mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
        else:
            mape = 0.0
        
        return {
            'rmse': float(rmse),
            'mae': float(mae),
            'mape': float(mape),
            'mse': float(mse)
        }
    
    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        return f"{self.__class__.__name__}(status={status}, config={self.config})"


class ModelRegistry:
    """模型注册中心
    
    使用装饰器模式自动注册模型类型，支持动态加载。
    
    Example:
        @ModelRegistry.register("sarima")
        class SARIMAModel(BaseTimeSeriesModel):
            pass
        
        # 获取模型类
        model_class = ModelRegistry.get("sarima")
        model = model_class(order=(1,1,1))
    """
    
    _registry: Dict[str, Type[BaseTimeSeriesModel]] = {}
    
    @classmethod
    def register(cls, model_type: str):
        """注册模型装饰器
        
        Args:
            model_type: 模型类型标识（如 "gradient_boosting", "prophet"）
            
        Returns:
            装饰器函数
        """
        def decorator(model_class: Type[BaseTimeSeriesModel]):
            if not issubclass(model_class, BaseTimeSeriesModel):
                raise TypeError(
                    f"{model_class.__name__} 必须继承自 BaseTimeSeriesModel"
                )
            
            if model_type in cls._registry:
                logger.warning(
                    f"模型类型 '{model_type}' 已存在，将被覆盖: "
                    f"{cls._registry[model_type].__name__} -> {model_class.__name__}"
                )
            
            cls._registry[model_type] = model_class
            logger.debug(f"注册模型: {model_type} -> {model_class.__name__}")
            return model_class
        
        return decorator
    
    @classmethod
    def get(cls, model_type: str) -> Type[BaseTimeSeriesModel]:
        """获取已注册的模型类
        
        Args:
            model_type: 模型类型标识
            
        Returns:
            模型类
            
        Raises:
            ValueError: 模型类型未注册
        """
        if model_type not in cls._registry:
            available = ', '.join(cls._registry.keys())
            raise ValueError(
                f"未注册的模型类型: '{model_type}'. "
                f"可用模型: {available}"
            )
        
        return cls._registry[model_type]
    
    @classmethod
    def list_models(cls) -> list[str]:
        """列出所有已注册的模型类型
        
        Returns:
            模型类型列表
        """
        return list(cls._registry.keys())
    
    @classmethod
    def is_registered(cls, model_type: str) -> bool:
        """检查模型是否已注册
        
        Args:
            model_type: 模型类型标识
            
        Returns:
            是否已注册
        """
        return model_type in cls._registry
    
    @classmethod
    def clear(cls):
        """清空注册表（主要用于测试）"""
        cls._registry.clear()
        logger.debug("模型注册表已清空")
