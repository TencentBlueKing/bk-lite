"""模型模块."""

from .base import BaseObjectDetectionModel, ModelRegistry
from .yolo_model import YOLOv11DetectionModel
from .yolo_wrapper import YOLODetectionWrapper

__all__ = [
    "BaseObjectDetectionModel",
    "ModelRegistry",
    "YOLOv11DetectionModel",
    "YOLODetectionWrapper",
]
