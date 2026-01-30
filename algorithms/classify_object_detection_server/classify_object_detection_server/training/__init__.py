"""训练模块 - 目标检测模型训练."""

from .trainer import UniversalTrainer
from .config.loader import TrainingConfig

__all__ = ["UniversalTrainer", "TrainingConfig"]
