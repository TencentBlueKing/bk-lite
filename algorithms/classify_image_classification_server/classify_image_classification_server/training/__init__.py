"""Training module for image classification."""

from .trainer import UniversalTrainer
from .config.loader import TrainingConfig

__all__ = ["UniversalTrainer", "TrainingConfig"]
