"""日志聚类训练模块

提供统一的训练流程和模型管理。
"""

from .trainer import UniversalTrainer
from .config.loader import TrainingConfig

__all__ = [
    "UniversalTrainer",
    "TrainingConfig",
]
