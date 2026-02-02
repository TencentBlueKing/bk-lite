"""Dummy model for demonstration and testing."""

import pandas as pd
import numpy as np
from loguru import logger


class DummyModel:
    """模拟文本分类模型,返回随机预测结果（用于开发和测试）."""

    def __init__(self):
        self.version = "0.1.0-dummy"
        self.classes_ = ["类别A", "类别B", "类别C"]  # 模拟类别
        logger.info(f"DummyModel initialized with classes: {self.classes_}")

    def predict(self, context=None, model_input=None):
        """
        模拟批量预测（MLflow PyFunc接口）.

        Args:
            context: MLflow上下文（未使用）
            model_input: 输入数据，可以是DataFrame、list或str

        Returns:
            预测结果DataFrame，包含prediction, probability等列
        """
        # 提取文本
        if isinstance(model_input, pd.DataFrame):
            texts = model_input["text"].tolist() if "text" in model_input.columns else model_input.iloc[:, 0].tolist()
        elif isinstance(model_input, pd.Series):
            texts = model_input.tolist()
        elif isinstance(model_input, list):
            texts = model_input
        elif isinstance(model_input, str):
            texts = [model_input]
        else:
            raise TypeError(f"Unsupported input type: {type(model_input)}")
        
        num_samples = len(texts)
        num_classes = len(self.classes_)
        
        logger.debug(f"DummyModel predicting {num_samples} samples")
        
        # 生成随机预测
        predictions_encoded = np.random.randint(0, num_classes, size=num_samples)
        predictions = [self.classes_[i] for i in predictions_encoded]
        
        # 生成随机概率（确保和为1）
        probabilities = np.random.dirichlet(np.ones(num_classes), size=num_samples)
        max_probs = probabilities.max(axis=1)
        
        # 构建结果DataFrame
        results = pd.DataFrame({
            "prediction": predictions,
            "prediction_encoded": predictions_encoded,
            "probability": max_probs,
        })
        
        # 添加各类别概率
        for i, class_name in enumerate(self.classes_):
            results[f"prob_{class_name}"] = probabilities[:, i]
        
        logger.debug(f"DummyModel prediction complete: {results.shape}")
        return results
