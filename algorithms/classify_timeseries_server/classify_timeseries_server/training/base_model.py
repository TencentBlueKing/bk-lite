"""时间序列训练基类."""

import abc
from typing import Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from loguru import logger


class BaseTimeSeriesModel(abc.ABC):
    """
    时间序列模型基类，提供通用的训练功能.
    
    Note:
        本基类专注于模型训练和离线评估。
        生产环境的在线预测请使用 serving 模块。
    """
    
    def __init__(self):
        self.frequency = None
        self.feature_cols = None
    
    @abc.abstractmethod
    def build_model(self, train_params: dict):
        """
        构建模型实例.
        
        Args:
            train_params: 训练参数字典
            
        Returns:
            模型实例
        """
        pass
    
    def preprocess(
        self, 
        df: pd.DataFrame, 
        frequency: Optional[str] = None
    ) -> Tuple[pd.DataFrame, str]:
        """
        数据预处理：时间标准化、排序、缺失值填充.
        
        Args:
            df: 包含 'date' 和 'value' 列的数据框
            frequency: 时间频率，如 'D', 'H', 'min' 等
            
        Returns:
            (处理后的数据框, 推断的频率)
        """
        if df is None or df.empty:
            return None, frequency
        
        df = df.copy()
        
        # 标准化时间列并排序
        if 'date' not in df.columns:
            raise ValueError("DataFrame must contain 'date' column")
        
        if not np.issubdtype(df["date"].dtype, np.datetime64):
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        
        df = df.dropna(subset=["date"]).sort_values("date")
        
        # 设置时间索引，推断频率
        df = df.set_index("date")
        if frequency is None:
            try:
                frequency = pd.infer_freq(df.index)
                if frequency:
                    logger.info(f"推断频率: {frequency}")
            except Exception as e:
                logger.warning(f"无法推断频率: {e}")
                frequency = None
        
        # 处理缺失值：时间插值 -> 前后填充 -> 中位数兜底
        if 'value' in df.columns:
            value_series = df["value"].astype(float)
            value_series = value_series.interpolate(method="time", limit_direction="both")
            value_series = value_series.ffill().bfill()
            
            if value_series.isna().any():
                median_value = value_series.median() if not np.isnan(value_series.median()) else 0.0
                value_series = value_series.fillna(median_value)
                logger.warning(f"使用中位数 {median_value} 填充了 {value_series.isna().sum()} 个 NaN 值")
            
            df["value"] = value_series
        
        df = df.reset_index()
        
        return df, frequency
    
    @abc.abstractmethod
    def train(
        self,
        model_name: str,
        train_dataframe: pd.DataFrame,
        val_dataframe: Optional[pd.DataFrame] = None,
        test_dataframe: Optional[pd.DataFrame] = None,
        train_config: dict = {},
        mlflow_tracking_url: Optional[str] = None,
        experiment_name: str = "Default",
        **kwargs
    ) -> Dict[str, Any]:
        """
        训练模型.
        
        Args:
            model_name: 模型名称
            train_dataframe: 训练数据
            val_dataframe: 验证数据（可选）
            test_dataframe: 测试数据（可选）
            train_config: 训练配置
            mlflow_tracking_url: MLflow tracking 地址
            experiment_name: 实验名称
            **kwargs: 其他参数
            
        Returns:
            训练结果字典，包含:
            - model: 训练好的模型实例
            - test_metrics: 测试集评估指标
            - run_id: MLflow run ID
            - 其他模型特定信息
            
        Note:
            训练后的模型会自动保存到 MLflow。
            生产环境的预测请使用 serving 模块加载模型。
        """
        pass
