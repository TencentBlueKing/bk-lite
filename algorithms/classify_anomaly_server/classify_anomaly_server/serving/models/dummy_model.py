"""Dummy model for demonstration and testing."""

import pandas as pd
import numpy as np
from loguru import logger


class DummyModel:
    """模拟异常检测模型,返回简单的规则检测结果."""

    def __init__(self):
        self.version = "0.1.0-dummy"
        logger.info("DummyModel initialized for anomaly detection")

    def predict(self, model_input: dict) -> dict:
        """
        模拟异常检测（统一接口）.

        Args:
            model_input: 模型输入字典
                - data: pd.Series 时间序列数据
                - threshold: Optional[float] 异常阈值（默认 0.7）

        Returns:
            检测结果字典（与 MLflow Wrapper 一致）:
                - labels: list[int] 标签列表 (0=正常, 1=异常)
                - scores: list[float] 异常分数列表 (0-1之间)
        """
        series = model_input.get('data')
        threshold = model_input.get('threshold', 0.7)
        
        if not isinstance(series, pd.Series):
            raise ValueError(f"Expected pd.Series, got {type(series)}")
        
        # 简单规则：计算每个点与均值的偏离程度
        mean_val = series.mean()
        std_val = series.std()
        
        if std_val == 0:
            # 所有值相同，无异常
            labels = [0] * len(series)
            scores = [0.0] * len(series)
        else:
            # 计算标准化偏离度作为异常分数
            z_scores = np.abs((series - mean_val) / std_val)
            # 映射到 0-1 范围（使用sigmoid函数）
            scores = (1 / (1 + np.exp(-z_scores + 2))).tolist()
            # 根据阈值判定异常
            labels = [1 if score > threshold else 0 for score in scores]
        
        anomaly_count = sum(labels)
        logger.debug(
            f"DummyModel detect: {len(series)} points, "
            f"{anomaly_count} anomalies, threshold={threshold}"
        )
        
        return {
            'labels': labels,
            'scores': scores
        }
