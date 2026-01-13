"""模型定义模块"""

# 导入所有模型类，确保装饰器被执行，模型被注册到 ModelRegistry
from .base import BaseTextClassifier, ModelRegistry
from .xgboost_model import XGBoostTextClassifier

__all__ = [
    "BaseTextClassifier",
    "ModelRegistry",
    "XGBoostTextClassifier",
]