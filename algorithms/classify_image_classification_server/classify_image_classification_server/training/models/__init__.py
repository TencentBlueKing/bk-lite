"""Model implementations."""

from .base import BaseImageClassificationModel, ModelRegistry
from .yolo_model import YOLOClassificationModel  # 导入以触发注册装饰器

__all__ = [
    "BaseImageClassificationModel", 
    "ModelRegistry",
    "YOLOClassificationModel"
]
