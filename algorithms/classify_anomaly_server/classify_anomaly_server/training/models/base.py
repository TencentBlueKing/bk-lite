"""异常检测模型基类和注册机制."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Type, Tuple
import pandas as pd
import numpy as np
from loguru import logger
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)


class BaseAnomalyModel(ABC):
    """异常检测模型基类 - 统一接口
    
    所有异常检测模型必须实现此接口，确保可以被通用训练器调用。
    
    核心方法：
    - fit(): 训练模型（通常使用正常样本）
    - predict(): 预测异常标签
    - predict_proba(): 预测异常分数
    - evaluate(): 评估模型性能
    
    工具方法：
    - get_params(): 获取模型参数
    """
    
    def __init__(self, **kwargs):
        """初始化模型
        
        Args:
            **kwargs: 模型特定的参数
        """
        self.model = None
        self.config = kwargs
        self.is_fitted = False
        self.contamination = kwargs.get('contamination', 0.1)
        self.threshold_ = None  # 异常阈值
    
    @abstractmethod
    def fit(self, 
            train_data: pd.DataFrame,
            val_data: Optional[pd.DataFrame] = None,
            **kwargs) -> 'BaseAnomalyModel':
        """训练模型
        
        Args:
            train_data: 训练数据（特征矩阵）
            val_data: 验证数据（可选，用于超参数优化）
            **kwargs: 模型特定的训练参数
            
        Returns:
            self: 训练后的模型实例
            
        Raises:
            ValueError: 数据格式不正确
        """
        pass
    
    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """预测异常标签
        
        Args:
            X: 特征矩阵
            
        Returns:
            预测标签数组（0=正常, 1=异常）
            
        Raises:
            RuntimeError: 模型未训练
        """
        pass
    
    @abstractmethod
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """预测异常分数
        
        Args:
            X: 特征矩阵
            
        Returns:
            异常分数数组（值越大越异常）
            
        Raises:
            RuntimeError: 模型未训练
        """
        pass
    
    def evaluate(self, 
                 test_data: pd.DataFrame,
                 test_labels: np.ndarray,
                 prefix: str = "") -> Dict[str, float]:
        """评估模型性能
        
        Args:
            test_data: 测试数据特征矩阵
            test_labels: 真实标签（0=正常, 1=异常）
            prefix: 指标名称前缀（如 "train", "test", "final_train"）
            
        Returns:
            评估指标字典，包含：
            - precision: 精确率
            - recall: 召回率
            - f1: F1分数
            - auc: ROC AUC（如果可计算）
            - confusion_matrix: 混淆矩阵
            
        Raises:
            RuntimeError: 模型未训练
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before evaluation")
        
        # 预测
        y_pred = self.predict(test_data)
        y_scores = self.predict_proba(test_data)
        
        # 计算指标
        metrics = {
            'precision': float(precision_score(test_labels, y_pred, zero_division=0)),
            'recall': float(recall_score(test_labels, y_pred, zero_division=0)),
            'f1': float(f1_score(test_labels, y_pred, zero_division=0)),
        }
        
        # 尝试计算 AUC
        try:
            metrics['auc'] = float(roc_auc_score(test_labels, y_scores))
        except ValueError as e:
            logger.warning(f"Cannot compute AUC: {e}")
            metrics['auc'] = 0.0
        
        # 混淆矩阵
        cm = confusion_matrix(test_labels, y_pred)
        metrics['confusion_matrix'] = cm.tolist()
        
        # 真负例、假正例、假负例、真正例
        if cm.shape == (2, 2):
            tn, fp, fn, tp = cm.ravel()
            metrics['true_negative'] = int(tn)
            metrics['false_positive'] = int(fp)
            metrics['false_negative'] = int(fn)
            metrics['true_positive'] = int(tp)
        
        # 存储预测结果和真实标签（用于后续分析）
        metrics['_predictions'] = y_pred.tolist()
        metrics['_scores'] = y_scores.tolist()
        metrics['_true_labels'] = test_labels.tolist()
        
        # 应用前缀（如果提供）
        if prefix:
            metrics = {f"{prefix}_{k}" if not k.startswith('_') else k: v for k, v in metrics.items()}
        
        return metrics
    
    def get_params(self) -> Dict[str, Any]:
        """获取模型参数
        
        Returns:
            模型参数字典
        """
        return self.config.copy()
    
    def _check_fitted(self):
        """检查模型是否已训练"""
        if not self.is_fitted:
            raise RuntimeError(
                "This model instance is not fitted yet. "
                "Call 'fit' with appropriate arguments before using this method."
            )


class ModelRegistry:
    """模型注册器 - 支持动态模型加载
    
    使用装饰器模式注册模型类：
    
    Example:
        @ModelRegistry.register("ECOD")
        class ECODModel(BaseAnomalyModel):
            pass
        
        # 动态创建模型
        model = ModelRegistry.create_model("ECOD", contamination=0.1)
    """
    
    _registry: Dict[str, Type[BaseAnomalyModel]] = {}
    
    @classmethod
    def register(cls, model_type: str):
        """注册模型类的装饰器
        
        Args:
            model_type: 模型类型标识（如 "ECOD", "IsolationForest"）
            
        Returns:
            装饰器函数
        """
        def decorator(model_class: Type[BaseAnomalyModel]):
            if not issubclass(model_class, BaseAnomalyModel):
                raise TypeError(
                    f"Model class must inherit from BaseAnomalyModel, "
                    f"got {model_class}"
                )
            
            cls._registry[model_type.lower()] = model_class
            logger.debug(f"Registered model: {model_type} -> {model_class.__name__}")
            return model_class
        
        return decorator
    
    @classmethod
    def get(cls, model_type: str) -> Type[BaseAnomalyModel]:
        """获取已注册的模型类（兼容timeseries_server API）
        
        Args:
            model_type: 模型类型（如 "ECOD"）
            
        Returns:
            模型类
            
        Raises:
            ValueError: 模型类型未注册
        """
        model_type_lower = model_type.lower()
        
        if model_type_lower not in cls._registry:
            available = ', '.join(cls._registry.keys())
            raise ValueError(
                f"Unknown model type: '{model_type}'. "
                f"Available models: {available}"
            )
        
        return cls._registry[model_type_lower]
    
    @classmethod
    def create_model(cls, model_type: str, **kwargs) -> BaseAnomalyModel:
        """创建模型实例
        
        Args:
            model_type: 模型类型（如 "ECOD"）
            **kwargs: 模型初始化参数
            
        Returns:
            模型实例
            
        Raises:
            ValueError: 模型类型未注册
        """
        model_class = cls.get(model_type)
        logger.info(f"Creating model: {model_type} ({model_class.__name__})")
        
        return model_class(**kwargs)
    
    @classmethod
    def list_models(cls) -> list[str]:
        """列出所有已注册的模型
        
        Returns:
            模型类型列表
        """
        return list(cls._registry.keys())
