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
    
    def predict(self, context, model_input) -> dict:
        """预测接口
        
        Args:
            context: MLflow context
            model_input: 字典格式 {'data': pd.Series, 'threshold': float (可选)}
            
        Returns:
            字典格式 {'labels': [0,1,...], 'scores': [0.1,0.9,...]}
        """
        # 解析输入
        data, threshold = self._parse_input(model_input)
        
        # 转换为 DataFrame（内部处理）
        if isinstance(data, pd.Series):
            df = pd.DataFrame({'value': data.values}, index=data.index)
        elif isinstance(data, pd.DataFrame):
            df = data
        else:
            raise ValueError(f"data 必须是 pd.Series 或 pd.DataFrame，实际类型: {type(data)}")
        
        # 检查特征（如果是 DataFrame 且指定了特征名）
        if isinstance(data, pd.DataFrame) and df.shape[1] != len(self.feature_names):
            raise ValueError(
                f"特征数量不匹配: 期望 {len(self.feature_names)}，"
                f"实际 {df.shape[1]}"
            )
        
        # 预测异常分数
        scores = self.model.decision_function(df)
        
        # 根据阈值判断异常
        predictions = (scores > threshold).astype(int)
        
        # 返回字典格式（与 DummyModel 一致）
        return {
            'labels': predictions.tolist(),
            'scores': scores.tolist()
        }
    
    def _parse_input(self, model_input) -> tuple:
        """解析输入数据
        
        Args:
            model_input: 字典格式 {'data': pd.Series, 'threshold': float (可选)}
            
        Returns:
            (data, threshold) 元组
        """
        if isinstance(model_input, dict):
            data = model_input.get('data')
            threshold = model_input.get('threshold', self.threshold)
            
            if data is None:
                raise ValueError("输入必须包含 'data' 字段")
            
            return data, threshold
        else:
            raise ValueError("输入格式错误，需要 dict 类型")
