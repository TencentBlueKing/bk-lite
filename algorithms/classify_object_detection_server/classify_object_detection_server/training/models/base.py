"""目标检测模型基类和注册器."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from loguru import logger


class BaseObjectDetectionModel(ABC):
    """目标检测模型抽象基类.

    定义所有目标检测模型必须实现的接口。
    """

    @abstractmethod
    def fit(
        self,
        dataset_yaml: str,
        val_data: Optional[str] = None,
        device: str = "auto",
        **kwargs,
    ) -> "BaseObjectDetectionModel":
        """
        训练模型.

        Args:
            dataset_yaml: YOLO格式数据集配置文件路径（data.yaml 或 dataset.yaml，包含train/val/test路径和类别信息）
            val_data: 验证集配置（可选，通常包含在dataset_yaml中）
            device: 设备配置（'auto', 'cpu', 'gpu', 'gpus', '0,1,2'等）
            **kwargs: 其他训练参数

        Returns:
            self: 训练后的模型实例
        """
        pass

    @abstractmethod
    def predict(self, X: Any) -> List[Dict[str, Any]]:
        """
        批量预测.

        Args:
            X: 输入数据（图片路径列表、PIL Image列表或numpy数组）

        Returns:
            预测结果列表，每个元素为字典格式：
            {
                'boxes': [[x1, y1, x2, y2], ...],  # 边界框坐标（归一化或绝对坐标）
                'classes': [class_id, ...],         # 类别ID
                'confidences': [conf, ...],         # 置信度
                'labels': [label_name, ...]         # 类别名称（可选）
            }
        """
        pass

    @abstractmethod
    def evaluate(self, test_data: str, prefix: str = "test") -> Dict[str, float]:
        """
        评估模型性能.

        Args:
            test_data: 测试数据集配置文件路径（YOLO格式）
            prefix: 指标名称前缀（如"test_", "val_"）

        Returns:
            评估指标字典，格式为：
            {
                f"{prefix}_map50": mAP@0.5,
                f"{prefix}_map": mAP@0.5:0.95,
                f"{prefix}_precision": 精确率,
                f"{prefix}_recall": 召回率
            }
            可包含以_开头的内部数据（如_per_class_metrics），这些不会被MLflow记录
        """
        pass

    @abstractmethod
    def optimize_hyperparams(
        self, train_data: str, val_data: str, max_evals: int
    ) -> Dict[str, Any]:
        """
        超参数优化（使用Hyperopt）.

        Args:
            train_data: 训练数据集配置文件路径
            val_data: 验证数据集配置文件路径（用于评估）
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
            @ModelRegistry.register("YOLODetection")
            class YOLODetectionModel(BaseObjectDetectionModel):
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
                f"未注册的模型类型: '{model_type}'\n可用的模型类型: {available_models}"
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
    def create(cls, model_type: str, **kwargs) -> BaseObjectDetectionModel:
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
