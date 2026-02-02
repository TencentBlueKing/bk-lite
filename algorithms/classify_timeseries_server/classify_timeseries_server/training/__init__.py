"""训练模块 - 重构版本

提供统一的模型训练接口和配置管理。
"""

from .data_loader import load_dataset
from .trainer import UniversalTrainer
from .config.loader import TrainingConfig
from .models import ModelRegistry
from .mlflow_utils import MLFlowUtils

__all__ = [
    # 核心接口
    "UniversalTrainer",
    "TrainingConfig",
    
    # 模型
    "ModelRegistry",
    
    # 工具类
    "load_dataset",
    "MLFlowUtils",
]
