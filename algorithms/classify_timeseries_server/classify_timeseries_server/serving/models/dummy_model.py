"""Dummy model for demonstration and testing."""

from loguru import logger


class DummyModel:
    """模拟模型,返回固定的预测结果."""

    def __init__(self):
        self.version = "0.1.0-dummy"
        logger.info("DummyModel initialized")

    def predict(self, features: dict[str, float]) -> float:
        """
        模拟预测.

        Args:
            features: 特征字典

        Returns:
            预测结果(所有特征值的和)
        """
        result = sum(features.values())
        logger.debug(f"DummyModel predict: {features} -> {result}")
        return result
