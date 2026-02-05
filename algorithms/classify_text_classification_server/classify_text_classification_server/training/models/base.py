"""模型基类和注册器"""
from abc import ABC, abstractmethod
from typing import Dict, Type, Any, Optional
from loguru import logger


class BaseTextClassifier(ABC):
    """文本分类器基类
    
    定义了文本分类模型的标准接口，所有具体模型必须实现这些方法。
    """
    
    @abstractmethod
    def fit(self, X_train, y_train, X_val=None, y_val=None, **kwargs):
        """训练模型
        
        Args:
            X_train: 训练集特征矩阵（稀疏矩阵或密集矩阵）
            y_train: 训练集标签（编码后的整数）
            X_val: 验证集特征矩阵（可选）
            y_val: 验证集标签（可选）
            **kwargs: 其他训练参数
            
        Returns:
            self
        """
        pass
    
    @abstractmethod
    def predict(self, X):
        """预测类别
        
        Args:
            X: 特征矩阵
            
        Returns:
            预测的类别标签（整数数组）
        """
        pass
    
    @abstractmethod
    def predict_proba(self, X):
        """预测类别概率
        
        Args:
            X: 特征矩阵
            
        Returns:
            类别概率矩阵 (n_samples, n_classes)
        """
        pass
    
    @abstractmethod
    def evaluate(self, X_test, y_test, prefix: str = "test") -> Dict[str, float]:
        """评估模型性能
        
        Args:
            X_test: 测试集特征矩阵
            y_test: 测试集标签
            prefix: 指标名称前缀（如 "train", "val", "test"）
            
        Returns:
            评估指标字典，格式: {f"{prefix}_metric_name": value}
            必须包含的指标：
            - accuracy: 准确率
            - f1_weighted: 加权 F1 分数
            - f1_macro: 宏平均 F1 分数
            - precision_weighted: 加权精确率
            - recall_weighted: 加权召回率
            - _confusion_matrix: 混淆矩阵（带下划线前缀，不记录到 MLflow）
        """
        pass
    
    @abstractmethod
    def optimize_hyperparams(
        self,
        X_train,
        y_train,
        X_val,
        y_val,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """优化超参数
        
        Args:
            X_train: 训练集特征矩阵
            y_train: 训练集标签
            X_val: 验证集特征矩阵
            y_val: 验证集标签
            config: 超参数优化配置
                - max_evals: 最大评估次数
                - metric: 优化目标指标（如 "f1_weighted"）
                - search_space: 搜索空间定义
                - random_state: 随机种子
                
        Returns:
            最优超参数字典
        """
        pass
    
    @abstractmethod
    def save_mlflow(self, artifact_path: str = "model"):
        """保存模型到 MLflow
        
        Args:
            artifact_path: MLflow 中的 artifact 路径
        """
        pass


class ModelRegistry:
    """模型注册器
    
    使用装饰器模式注册和创建模型实例。
    
    示例:
        @ModelRegistry.register("XGBoost")
        class XGBoostTextClassifier(BaseTextClassifier):
            pass
        
        model = ModelRegistry.create("XGBoost", **kwargs)
    """
    
    _registry: Dict[str, Type[BaseTextClassifier]] = {}
    
    @classmethod
    def register(cls, model_type: str):
        """注册模型的装饰器
        
        Args:
            model_type: 模型类型名称（如 "XGBoost", "RandomForest"）
            
        Returns:
            装饰器函数
        """
        def decorator(model_class: Type[BaseTextClassifier]):
            if not issubclass(model_class, BaseTextClassifier):
                raise TypeError(f"模型类必须继承自 BaseTextClassifier: {model_class}")
            
            if model_type in cls._registry:
                logger.warning(f"模型类型 '{model_type}' 已存在，将被覆盖")
            
            cls._registry[model_type] = model_class
            logger.info(f"注册模型: {model_type} -> {model_class.__name__}")
            
            return model_class
        
        return decorator
    
    @classmethod
    def create(cls, model_type: str, **kwargs) -> BaseTextClassifier:
        """创建模型实例
        
        Args:
            model_type: 模型类型名称
            **kwargs: 传递给模型构造函数的参数
            
        Returns:
            模型实例
            
        Raises:
            ValueError: 模型类型未注册
        """
        if model_type not in cls._registry:
            available_models = list(cls._registry.keys())
            raise ValueError(f"未注册的模型类型: '{model_type}'. "
                           f"可用模型: {available_models}")
        
        model_class = cls._registry[model_type]
        logger.info(f"创建模型实例: {model_type}")
        
        return model_class(**kwargs)
    
    @classmethod
    def list_models(cls) -> list:
        """列出所有已注册的模型类型
        
        Returns:
            模型类型名称列表
        """
        return list(cls._registry.keys())
    
    @classmethod
    def get_model_class(cls, model_type: str) -> Type[BaseTextClassifier]:
        """获取模型类
        
        Args:
            model_type: 模型类型名称
            
        Returns:
            模型类
            
        Raises:
            ValueError: 模型类型未注册
        """
        if model_type not in cls._registry:
            raise ValueError(f"未注册的模型类型: '{model_type}'")
        
        return cls._registry[model_type]
