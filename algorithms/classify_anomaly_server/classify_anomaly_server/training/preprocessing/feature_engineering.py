"""异常检测特征工程

专为异常检测设计的特征提取器。
核心思想：捕捉数据的统计分布特征和时间模式特征。
"""

from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np
from loguru import logger
from feature_engine.timeseries.forecasting import LagFeatures, WindowFeatures


class AnomalyFeatureEngineer:
    """异常检测特征工程器
    
    专为异常检测优化的特征提取：
    1. 滚动窗口统计特征（最重要）- 捕捉局部分布
    2. 时间特征 - 捕捉周期性模式
    3. 简化的滞后特征 - 捕捉短期依赖
    4. 差分特征 - 捕捉突变
    
    与时间序列预测的区别：
    - 更关注统计特征（均值、标准差、极值）
    - 不需要太多滞后期（3-7期即可）
    - 时间特征用于捕捉周期性异常模式
    
    使用示例：
        engineer = AnomalyFeatureEngineer(
            rolling_windows=[12, 24, 48],
            lag_periods=[1, 2, 3]
        )
        X = engineer.fit_transform(data)
    """
    
    def __init__(
        self,
        rolling_windows: Optional[List[int]] = None,
        rolling_features: Optional[List[str]] = None,
        lag_periods: Optional[List[int]] = None,
        use_temporal_features: bool = True,
        use_diff_features: bool = True,
        diff_periods: Optional[List[int]] = None,
        drop_na: bool = True,
        **kwargs
    ):
        """初始化特征工程器
        
        Args:
            rolling_windows: 滚动窗口大小列表，如 [12, 24, 48]
            rolling_features: 滚动窗口统计特征，如 ['mean', 'std', 'min', 'max']
            lag_periods: 滞后期列表，如 [1, 2, 3]（建议不超过7）
            use_temporal_features: 是否提取时间特征
            use_diff_features: 是否使用差分特征
            diff_periods: 差分期数，如 [1]
            drop_na: 是否删除包含NaN的行
            **kwargs: 其他参数
        """
        # 默认配置：为异常检测优化
        self.rolling_windows = rolling_windows or [12, 24, 48]
        self.rolling_features = rolling_features or ['mean', 'std', 'min', 'max']
        self.lag_periods = lag_periods or [1, 2, 3]
        self.use_temporal_features = use_temporal_features
        self.use_diff_features = use_diff_features
        self.diff_periods = diff_periods or [1]
        self.drop_na = drop_na
        
        # Feature-engine 转换器
        self.lag_transformer = None
        self.window_transformer = None
        
        # 特征列名记录
        self.feature_names_ = []
        self.is_fitted = False
        
        logger.debug(
            f"特征工程器初始化: "
            f"rolling_windows={self.rolling_windows}, "
            f"lag_periods={self.lag_periods}, "
            f"temporal={self.use_temporal_features}"
        )
    
    def fit(self, data: pd.Series) -> 'AnomalyFeatureEngineer':
        """拟合特征工程器
        
        Args:
            data: 时间序列数据（带 DatetimeIndex 的 Series）
            
        Returns:
            self
        """
        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("数据必须有 DatetimeIndex")
        
        logger.debug(f"拟合特征工程器，数据点: {len(data)}")
        
        # 转换为DataFrame
        df = pd.DataFrame({'value': data})
        
        # 初始化转换器
        self._fit_transformers(df)
        
        self.is_fitted = True
        logger.debug("特征工程器拟合完成")
        
        return self
    
    def transform(self, data: pd.Series) -> pd.DataFrame:
        """转换数据为特征矩阵
        
        Args:
            data: 时间序列数据
            
        Returns:
            特征矩阵（不包含目标列）
        """
        if not self.is_fitted:
            raise RuntimeError("特征工程器未拟合，请先调用 fit()")
        
        # 转换为DataFrame
        df = pd.DataFrame({'value': data})
        
        # 应用转换
        df_features = self._apply_transformations(df)
        
        # 只返回特征，不包含原始 value
        X = df_features.drop('value', axis=1)
        
        # 删除NaN行
        if self.drop_na:
            valid_mask = ~X.isna().any(axis=1)
            X = X[valid_mask]
            logger.debug(f"删除NaN后剩余样本: {len(X)}")
        
        logger.debug(f"特征转换完成: X={X.shape}")
        
        return X
    
    def fit_transform(self, data: pd.Series) -> pd.DataFrame:
        """拟合并转换数据
        
        Args:
            data: 时间序列数据
            
        Returns:
            特征矩阵
        """
        self.fit(data)
        return self.transform(data)
    
    def _fit_transformers(self, df: pd.DataFrame):
        """初始化并拟合所有转换器"""
        
        # 1. 滞后特征
        if self.lag_periods:
            logger.debug(f"配置滞后特征: {self.lag_periods}")
            self.lag_transformer = LagFeatures(
                variables=['value'],
                periods=self.lag_periods,
                drop_original=False
            )
            self.lag_transformer.fit(df)
        
        # 2. 滚动窗口特征
        if self.rolling_windows:
            logger.debug(f"配置滚动窗口特征: windows={self.rolling_windows}")
            self.window_transformer = WindowFeatures(
                variables=['value'],
                window=self.rolling_windows,
                functions=self.rolling_features,
                drop_original=False
            )
            self.window_transformer.fit(df)
    
    def _apply_transformations(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用所有特征转换"""
        df_features = df.copy()
        
        # 1. 滞后特征
        if self.lag_transformer:
            df_features = self.lag_transformer.transform(df_features)
            logger.debug(f"滞后特征: {len(self.lag_periods)} 个")
        
        # 2. 滚动窗口特征
        if self.window_transformer:
            # 在原始value列上计算滚动窗口
            df_original_value = df[['value']].copy()
            df_window = self.window_transformer.transform(df_original_value)
            
            # 合并滚动窗口特征
            window_cols = [col for col in df_window.columns if col != 'value']
            for col in window_cols:
                df_features[col] = df_window[col]
            
            logger.debug(f"滚动窗口特征: {len(window_cols)} 个")
        
        # 3. 时间特征
        if self.use_temporal_features and isinstance(df_features.index, pd.DatetimeIndex):
            df_features = self._extract_temporal_features(df_features)
            logger.debug("时间特征已提取")
        
        # 4. 差分特征
        if self.use_diff_features:
            df_features = self._add_diff_features(df_features)
            logger.debug(f"差分特征: {len(self.diff_periods)} 个")
        
        # 记录特征名（排除原始 value 列）
        self.feature_names_ = [col for col in df_features.columns if col != 'value']
        
        return df_features
    
    def _extract_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """提取时间特征
        
        为异常检测优化的时间特征：
        - 小时：捕捉日内模式
        - 星期：捕捉周模式
        - 月份：捕捉季节性
        - 是否周末：捕捉工作日vs周末差异
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            return df
        
        # 基础时间特征
        df['hour'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
        df['month'] = df.index.month
        df['day_of_month'] = df.index.day
        
        # 周末标记
        df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)
        
        # 时段（早中晚夜）
        df['time_of_day'] = pd.cut(
            df.index.hour,
            bins=[0, 6, 12, 18, 24],
            labels=[0, 1, 2, 3],  # 0=夜间, 1=早上, 2=中午, 3=晚上
            include_lowest=True
        ).astype(int)
        
        return df
    
    def _add_diff_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加差分特征
        
        差分特征可以捕捉突变，对异常检测很有用。
        """
        for period in self.diff_periods:
            col_name = f'value_diff_{period}'
            df[col_name] = df['value'].diff(period)
            
            # 添加差分的绝对值（突变幅度）
            df[f'{col_name}_abs'] = df[col_name].abs()
        
        return df
    
    def get_feature_names(self) -> List[str]:
        """获取特征名称列表
        
        Returns:
            特征名称列表
        """
        if not self.is_fitted:
            raise RuntimeError("特征工程器未拟合")
        
        return self.feature_names_.copy()
