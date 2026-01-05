"""ECOD 模型的 MLflow 推理包装器

此文件包含 ECOD 模型的 MLflow 包装器，用于模型推理服务。
"""

from typing import Optional
import pandas as pd
import numpy as np
import mlflow
from loguru import logger


class ECODWrapper(mlflow.pyfunc.PythonModel):
    """ECOD 模型的 MLflow 包装器
    
    用于 MLflow 模型保存和推理服务。
    """
    
    def __init__(
        self,
        model,
        feature_names: list,
        threshold: float
    ):
        """初始化包装器
        
        Args:
            model: 训练好的 ECOD 模型（pyod.models.ecod.ECOD）
            feature_names: 特征名称列表
            threshold: 异常阈值
        """
        self.model = model
        self.feature_names = feature_names
        self.threshold = threshold
        
        logger.debug(
            f"ECODWrapper 初始化: "
            f"features={len(feature_names)}, "
            f"threshold={threshold}"
        )
    
    def predict(self, context, model_input) -> pd.DataFrame:
        """预测接口
        
        Args:
            context: MLflow context
            model_input: 输入数据 (pd.DataFrame)
            
        Returns:
            包含异常分数和标签的 DataFrame
        """
        if not isinstance(model_input, pd.DataFrame):
            raise ValueError(f"输入必须是 pd.DataFrame，实际类型: {type(model_input)}")
        
        # 检查特征
        if model_input.shape[1] != len(self.feature_names):
            raise ValueError(
                f"特征数量不匹配: 期望 {len(self.feature_names)}，"
                f"实际 {model_input.shape[1]}"
            )
        
        # 预测异常分数
        scores = self.model.decision_function(model_input)
        
        # 根据阈值判断异常
        predictions = (scores > self.threshold).astype(int)
        
        # 返回结果
        result = pd.DataFrame({
            'anomaly_score': scores,
            'is_anomaly': predictions
        }, index=model_input.index)
        
        return result
