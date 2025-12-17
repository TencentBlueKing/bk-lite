"""Dummy model for demonstration and testing."""

from loguru import logger


class DummyModel:
    """模拟模型，返回简单的预测结果（用于测试和降级）."""

    def __init__(self):
        self.version = "0.1.0-dummy"
        logger.info("DummyModel initialized")

    def predict(self, features: dict) -> list:
        """
        模拟预测（兼容时间序列格式）.

        支持两种输入格式：
        1. 时间序列格式: {'history': [float], 'steps': int}
        2. 通用格式: {'feature1': float, 'feature2': float, ...}

        Args:
            features: 特征字典

        Returns:
            预测结果列表（时间序列格式）或单值（通用格式）
        """
        # 时间序列格式：返回列表
        if 'history' in features and 'steps' in features:
            steps = features.get('steps', 10)
            history = features.get('history', [])
            
            # 简单策略：重复最后一个观测值（naive forecast）
            if history and len(history) > 0:
                last_value = float(history[-1])
            else:
                last_value = 0.0
            
            result = [last_value] * steps
            logger.debug(
                f"DummyModel predict (time series): "
                f"history_len={len(history)}, steps={steps}, "
                f"forecast=[{last_value}] * {steps}"
            )
            return result
        
        # 通用格式：返回所有特征值的和（向后兼容）
        try:
            result = sum(features.values())
            logger.debug(f"DummyModel predict (generic): {features} -> {result}")
            return result
        except (TypeError, AttributeError):
            # 如果无法求和，返回默认值
            logger.warning(f"DummyModel: unable to sum features {features}, returning 0.0")
            return 0.0
