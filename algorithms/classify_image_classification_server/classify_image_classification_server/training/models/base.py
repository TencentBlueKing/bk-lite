"""图片分类模型基类和注册器."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List
from loguru import logger


class BaseImageClassificationModel(ABC):
    """图片分类模型抽象基类.
    
    定义所有图片分类模型必须实现的接口。
    """
    
    @abstractmethod
    def fit(self, train_data: Tuple[str, List[str]], 
            val_data: Optional[Tuple[str, List[str]]] = None,
            device: str = 'auto',
            **kwargs) -> 'BaseImageClassificationModel':
        """
        训练模型.
        
        Args:
            train_data: 训练数据，格式为(train_path, class_names)
                - train_path: 训练集目录路径（ImageFolder格式）
                - class_names: 类别名称列表
            val_data: 验证数据，格式同train_data（可选）
            device: 设备配置（'auto', 'cpu', 'gpu', 'gpus', '0,1,2'等）
            **kwargs: 其他训练参数
            
        Returns:
            self: 训练后的模型实例
        """
        pass
    
    @abstractmethod
    def predict(self, X: Any) -> List[int]:
        """
        批量预测.
        
        Args:
            X: 输入数据（图片路径列表、PIL Image列表或numpy数组）
            
        Returns:
            预测的类别索引列表
        """
        pass
    
    @abstractmethod
    def evaluate(self, test_data: Tuple[str, List[str]], 
                prefix: str = "test") -> Dict[str, float]:
        """
        评估模型性能.
        
        Args:
            test_data: 测试数据，格式为(test_path, class_names)
            prefix: 指标名称前缀（如"test_", "val_"）
            
        Returns:
            评估指标字典，格式为 {f"{prefix}_acc_top1": value, ...}
            可包含以_开头的内部数据（如_confusion_matrix），这些不会被MLflow记录
        """
        pass
    
    @abstractmethod
    def optimize_hyperparams(self, train_data: Tuple[str, List[str]],
                           val_data: Tuple[str, List[str]],
                           max_evals: int) -> Dict[str, Any]:
        """
        超参数优化（使用Hyperopt）.
        
        Args:
            train_data: 训练数据
            val_data: 验证数据（用于评估）
            max_evals: 最大评估次数
            
        Returns:
            最优超参数字典
        """
        pass
    
    @abstractmethod
    def save_mlflow(self, artifact_path: str = "model"):
        """
        保存模型到MLflow.
        
        Args:
            artifact_path: MLflow中的artifact路径
        """
        pass
    
    def get_params(self) -> Dict[str, Any]:
        """
        获取模型参数（可选实现）.
        
        Returns:
            模型参数字典
        """
        return {}
    
    def _check_fitted(self):
        """
        检查模型是否已训练（可选实现）.
        
        Raises:
            RuntimeError: 模型未训练
        """
        pass


class ModelRegistry:
    """模型注册器（单例模式）.
    
    用于注册和创建模型实例。
    """
    
    _models = {}
    
    @classmethod
    def register(cls, model_type: str):
        """
        模型注册装饰器.
        
        Usage:
            @ModelRegistry.register("YOLOClassification")
            class YOLOClassificationModel(BaseImageClassificationModel):
                ...
        
        Args:
            model_type: 模型类型标识符
            
        Returns:
            装饰器函数
        """
        def decorator(model_class):
            if model_type in cls._models:
                logger.warning(f"模型类型'{model_type}'已注册，将被覆盖")
            cls._models[model_type] = model_class
            logger.debug(f"模型类型'{model_type}'注册成功: {model_class.__name__}")
            return model_class
        return decorator
    
    @classmethod
    def get(cls, model_type: str) -> type:
        """
        获取模型类.
        
        Args:
            model_type: 模型类型标识符
            
        Returns:
            模型类
            
        Raises:
            ValueError: 模型类型未注册
        """
        if model_type not in cls._models:
            available_models = list(cls._models.keys())
            raise ValueError(
                f"未注册的模型类型: '{model_type}'\n"
                f"可用的模型类型: {available_models}"
            )
        return cls._models[model_type]
    
    @classmethod
    def list_models(cls) -> List[str]:
        """
        列出所有已注册的模型类型.
        
        Returns:
            模型类型列表
        """
        return list(cls._models.keys())
    
    @classmethod
    def create(cls, model_type: str, **kwargs) -> BaseImageClassificationModel:
        """
        创建模型实例.
        
        Args:
            model_type: 模型类型标识符
            **kwargs: 模型初始化参数
            
        Returns:
            模型实例
        """
        model_class = cls.get(model_type)
        return model_class(**kwargs)
