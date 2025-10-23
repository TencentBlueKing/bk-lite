"""时序特征工程模块"""
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from loguru import logger
from tsfresh import extract_relevant_features, extract_features
from tsfresh.feature_extraction import EfficientFCParameters


class TimeSeriesFeatureEngineer:
    """时序特征工程器"""
    
    def __init__(self, tsfresh_params: Optional[Dict] = None, n_jobs: int = 4):
        self.tsfresh_params = tsfresh_params or {}
        self.n_jobs = n_jobs
        
    def extract_features(
        self,
        df: pd.DataFrame,
        selected_features: Optional[List[str]] = None,
        extract_labels: bool = True
    ) -> Tuple[pd.DataFrame, Optional[pd.Series], List[str]]:
        """提取时序特征"""
        if df is None or df.empty:
            raise ValueError("输入数据为空")
            
        # 数据准备
        df = df.copy()
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        if extract_labels and "label" in df.columns:
            df["label"] = pd.to_numeric(df["label"], errors="coerce")
        
        # 时间戳处理
        if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        
        df = df.dropna(subset=["timestamp", "value"]).sort_values("timestamp").reset_index(drop=True)
        df["_id"] = df.index
        
        # 提取标签
        y = df["label"].astype(int) if extract_labels and "label" in df.columns else None
        
        # 特征提取
        fc_params = EfficientFCParameters()
        fc_params.update(self.tsfresh_params)
        
        timeseries_data = df[["_id", "timestamp", "value"]]
        
        try:
            if selected_features is None:
                # 训练模式：提取相关特征
                y.index = df["_id"]
                X = extract_relevant_features(
                    timeseries_container=timeseries_data,
                    y=y,
                    column_id="_id",
                    column_sort="timestamp", 
                    default_fc_parameters=fc_params,
                    n_jobs=self.n_jobs,
                    disable_progressbar=True,
                    show_warnings=False
                )
            else:
                # 推理模式：提取指定特征
                X_all = extract_features(
                    timeseries_container=timeseries_data,
                    column_id="_id",
                    column_sort="timestamp",
                    default_fc_parameters=fc_params,
                    n_jobs=self.n_jobs,
                    disable_progressbar=True,
                    show_warnings=False
                )
                
                # 匹配特征
                available_features = [f for f in selected_features if f in X_all.columns]
                X = X_all[available_features].copy() if available_features else pd.DataFrame(index=X_all.index)
                
                # 填充缺失特征
                for feat in selected_features:
                    if feat not in X.columns:
                        X[feat] = 0
                        
                X = X[selected_features]
                
        except Exception as e:
            logger.warning(f"特征提取失败: {e}, 使用基础特征")
            values = df['value']
            n_samples = len(df)
            X = pd.DataFrame({
                'value_mean': [values.mean()] * n_samples,
                'value_std': [values.std()] * n_samples,
                'value_min': [values.min()] * n_samples,
                'value_max': [values.max()] * n_samples
            })
        
        # 清理特征
        X = X.replace([np.inf, -np.inf], np.nan).fillna(0)
        
        if X.empty or X.shape[1] == 0:
            X = pd.DataFrame({'_fallback': [0] * len(df)})
        
        return X.reset_index(drop=True), (y.reset_index(drop=True) if y is not None else None), list(X.columns)

