"""日志聚类模型基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import pandas as pd
from loguru import logger


class BaseLogClusterModel(ABC):
    """日志聚类模型基类 - 统一接口
    
    所有日志聚类模型必须继承此基类并实现抽象方法。
    
    核心方法：
    - fit(): 训练模型
    - predict(): 预测聚类 ID
    - evaluate(): 评估模型性能
    
    工具方法：
    - get_params(): 获取模型参数
    - save()/load(): 模型持久化
    """

    def __init__(self, **kwargs):
        """初始化模型
        
        Args:
            **kwargs: 模型特定的配置参数
        """
        self.config = kwargs
        self.model = None
        self.templates = None
        self.is_trained = False

    @abstractmethod
    def fit(self, 
            train_data: List[str],
            val_data: Optional[List[str]] = None,
            verbose: bool = True,
            log_to_mlflow: bool = True,
            **kwargs) -> 'BaseLogClusterModel':
        """训练模型
        
        Args:
            train_data: 训练日志列表
            val_data: 验证日志列表（可选，用于超参数优化）
            verbose: 是否输出详细日志
            log_to_mlflow: 是否记录到 MLflow（超参数优化时设为 False）
            **kwargs: 其他训练参数
        
        Returns:
            self: 训练后的模型实例（支持链式调用）
        
        Raises:
            ValueError: 数据格式不正确
        """
        pass

    @abstractmethod
    def predict(self, logs: List[str]) -> List[int]:
        """预测日志的聚类 ID
        
        Args:
            logs: 日志消息列表
        
        Returns:
            聚类 ID 列表（模板 ID）
        
        Raises:
            RuntimeError: 模型未训练
        """
        pass

    def _check_fitted(self):
        """检查模型是否已训练
        
        Raises:
            RuntimeError: 模型未训练
        """
        if not self.is_trained:
            raise RuntimeError(
                f"{self.__class__.__name__} 模型未训练，请先调用 fit() 方法"
            )

    @abstractmethod
    def evaluate(
        self,
        logs: List[str],
        ground_truth: Optional[List[int]] = None,
        prefix: str = "",
        verbose: bool = True,
    ) -> Dict[str, float]:
        """评估模型性能
        
        子类必须实现此方法，返回评估指标字典。
        
        Args:
            logs: 日志消息列表
            ground_truth: 真实聚类标签（可选，用于监督评估）
            prefix: 指标名称前缀（如 "train", "test", "val"）
            verbose: 是否输出详细日志
        
        Returns:
            评估指标字典，建议包含以下指标：
            {
                "num_templates": int,           # 模板数量
                "coverage_rate": float,         # 覆盖率（解析成功率）
                "template_diversity": float,    # 模板多样性（归一化熵）
                # 如果提供 ground_truth，还应包含：
                "grouping_accuracy": float,     # 分组准确率
                "precision": float,             # 精确率
                "recall": float,                # 召回率
                "f1_score": float              # F1分数
            }
        
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
    
    def __repr__(self) -> str:
        """字符串表示
        
        Returns:
            模型的字符串表示
        """
        status = "trained" if self.is_trained else "not trained"
        num_templates = self.get_num_templates()
        return f"{self.__class__.__name__}(status={status}, templates={num_templates})"

    def save(self, output_path: str) -> None:
        """保存模型到文件
        
        Args:
            output_path: 输出文件路径
        
        Raises:
            RuntimeError: 模型未训练
        """
        self._check_fitted()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        model_data = {
            "config": self.config,
            "model": self.model,
            "templates": self.templates,
            "is_trained": self.is_trained,
        }

        joblib.dump(model_data, output_path)
        logger.info(f"模型已保存到 {output_path}")

    @classmethod
    def load(cls, model_path: str) -> "BaseLogClusterModel":
        """从文件加载模型
        
        Args:
            model_path: 模型文件路径
        
        Returns:
            加载的模型实例
        
        Raises:
            FileNotFoundError: 模型文件不存在
        """
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件未找到: {model_path}")

        model_data = joblib.load(model_path)

        # 创建实例
        instance = cls(**model_data["config"])
        instance.model = model_data["model"]
        instance.templates = model_data["templates"]
        instance.is_trained = model_data["is_trained"]

        logger.info(f"模型已从 {model_path} 加载")
        return instance

    def get_templates(self) -> Optional[List[str]]:
        """获取发现的日志模板
        
        Returns:
            日志模板列表
        """
        return self.templates

    def get_num_templates(self) -> int:
        """获取发现的模板数量
        
        Returns:
            模板数量
        """
        return len(self.templates) if self.templates else 0


class ModelRegistry:
    """模型注册器 - 支持动态模型加载
    
    使用装饰器模式注册模型类：
    
    Example:
        @ModelRegistry.register("Spell")
        class SpellModel(BaseLogClusterModel):
            pass
        
        # 动态创建模型
        model = ModelRegistry.create_model("Spell", tau=0.5)
    """

    _registry: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        """注册模型类的装饰器
        
        Args:
            name: 模型名称
        
        Returns:
            装饰器函数
        """

        def decorator(model_class: type) -> type:
            if not issubclass(model_class, BaseLogClusterModel):
                raise TypeError(
                    f"模型类必须继承自 BaseLogClusterModel，当前: {model_class}"
                )
            # 大小写不敏感
            cls._registry[name.lower()] = model_class
            logger.debug(f"注册模型: {name} -> {model_class.__name__}")
            return model_class

        return decorator

    @classmethod
    def get(cls, name: str) -> type:
        """获取已注册的模型类
        
        Args:
            name: 模型名称
        
        Returns:
            模型类
        
        Raises:
            ValueError: 模型未注册
        """
        name_lower = name.lower()
        
        if name_lower not in cls._registry:
            available = ', '.join(cls._registry.keys())
            raise ValueError(
                f"模型 '{name}' 未在注册表中找到。可用模型: {available}"
            )
        return cls._registry[name_lower]
    
    @classmethod
    def get_model_class(cls, name: str) -> type:
        """获取模型类（向后兼容方法）
        
        Args:
            name: 模型名称
        
        Returns:
            模型类
        """
        return cls.get(name)

    @classmethod
    def create_model(cls, name: str, **kwargs) -> BaseLogClusterModel:
        """创建模型实例
        
        Args:
            name: 模型名称
            **kwargs: 模型配置参数
        
        Returns:
            模型实例
        
        Raises:
            ValueError: 模型未注册
        """
        model_class = cls.get(name)
        logger.info(f"创建模型: {name} ({model_class.__name__})")
        return model_class(**kwargs)

    @classmethod
    def list_models(cls) -> List[str]:
        """列出所有已注册的模型
        
        Returns:
            模型名称列表
        """
        return list(cls._registry.keys())
    
    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查模型是否已注册
        
        Args:
            name: 模型名称
        
        Returns:
            是否已注册
        """
        return name.lower() in cls._registry
    
    @classmethod
    def clear(cls):
        """清空注册表（主要用于测试）"""
        cls._registry.clear()
        logger.debug("模型注册表已清空")
