"""通用时间序列特征工程

使用 feature-engine 和其他技术提供统一的时间序列特征提取。
支持多种特征类型：
- 滞后特征 (Lag Features)
- 滚动窗口统计特征 (Rolling Statistics)
- 时间特征 (Temporal Features)
- 周期性特征 (Cyclical Features)
- 差分特征 (Differencing Features)
"""

from typing import List, Optional, Dict, Any, Tuple
import pandas as pd
import numpy as np
from loguru import logger
from feature_engine.creation import CyclicalFeatures
from feature_engine.timeseries.forecasting import LagFeatures, WindowFeatures


class TimeSeriesFeatureEngineer:
    """时间序列特征工程器
    
    提供统一的特征提取接口，支持：
    1. 滞后特征：过去N个时间步的值
    2. 滚动窗口特征：均值、标准差、最大值、最小值等
    3. 时间特征：年、月、日、星期、小时等
    4. 周期性特征：季节性编码（sin/cos变换）
    5. 差分特征：一阶、二阶差分
    6. 交互特征：滞后特征的交互
    
    使用示例：
        engineer = TimeSeriesFeatureEngineer(
            lag_periods=[1, 2, 3, 7, 14],
            rolling_windows=[7, 14, 30],
            use_temporal_features=True
        )
        
        X, y = engineer.fit_transform(data)
    """
    
    def __init__(
        self,
        lag_periods: Optional[List[int]] = None,
        rolling_windows: Optional[List[int]] = None,
        rolling_features: Optional[List[str]] = None,
        use_temporal_features: bool = True,
        use_cyclical_features: bool = True,
        use_diff_features: bool = False,
        diff_periods: Optional[List[int]] = None,
        seasonal_period: Optional[int] = None,
        drop_na: bool = True,
        **kwargs
    ):
        """初始化特征工程器
        
        Args:
            lag_periods: 滞后期列表，如 [1, 2, 3, 7] 表示使用 t-1, t-2, t-3, t-7 的值
            rolling_windows: 滚动窗口大小列表，如 [7, 14] 表示7天和14天窗口
            rolling_features: 滚动窗口统计特征，如 ['mean', 'std', 'min', 'max']
            use_temporal_features: 是否提取时间特征（年、月、日、星期等）
            use_cyclical_features: 是否使用周期性编码（sin/cos）
            use_diff_features: 是否使用差分特征
            diff_periods: 差分期数，如 [1, 12] 表示一阶和季节性差分
            seasonal_period: 季节周期（用于周期性特征），如12表示月度季节性
            drop_na: 是否删除包含NaN的行
            **kwargs: 其他参数
        """
        self.lag_periods = lag_periods or [1, 2, 3, 7, 14]
        self.rolling_windows = rolling_windows or [7, 14, 30]
        self.rolling_features = rolling_features or ['mean', 'std', 'min', 'max']
        self.use_temporal_features = use_temporal_features
        self.use_cyclical_features = use_cyclical_features
        self.use_diff_features = use_diff_features
        self.diff_periods = diff_periods or [1]
        self.seasonal_period = seasonal_period or 12
        self.drop_na = drop_na
        
        # Feature-engine 转换器
        self.lag_transformer = None
        self.window_transformer = None
        self.cyclical_transformer = None
        
        # 特征列名记录
        self.feature_names_ = []
        self.is_fitted = False
        
        logger.debug(
            f"特征工程器初始化: "
            f"lag_periods={self.lag_periods}, "
            f"rolling_windows={self.rolling_windows}, "
            f"temporal={self.use_temporal_features}, "
            f"cyclical={self.use_cyclical_features}"
        )
    
    def fit(self, data: pd.Series) -> 'TimeSeriesFeatureEngineer':
        """拟合特征工程器
        
        Args:
            data: 时间序列数据（带 DatetimeIndex 的 Series）
            
        Returns:
            self
        """
        if not isinstance(data, pd.Series):
            raise ValueError("data 必须是 pandas.Series")
        
        if not isinstance(data.index, pd.DatetimeIndex):
            logger.warning("data 索引不是 DatetimeIndex，部分特征可能无法提取")
        
        logger.info("开始拟合特征工程器...")
        logger.info(f"数据长度: {len(data)}")
        
        # 转换为 DataFrame（feature-engine 需要）
        df = pd.DataFrame({
            'timestamp': data.index,
            'value': data.values
        })
        df.set_index('timestamp', inplace=True)
        
        # 初始化并拟合转换器
        self._fit_transformers(df)
        
        self.is_fitted = True
        logger.info(f"特征工程器拟合完成，特征总数: {len(self.feature_names_)}")
        
        return self
    
    def transform(self, data: pd.Series) -> Tuple[pd.DataFrame, pd.Series]:
        """转换数据为特征和目标
        
        Args:
            data: 时间序列数据
            
        Returns:
            (X, y): 特征矩阵和目标序列
        """
        if not self.is_fitted:
            raise RuntimeError("必须先调用 fit() 方法")
        
        # logger.debug("开始特征转换...")
        
        # 转换为 DataFrame
        df = pd.DataFrame({
            'timestamp': data.index,
            'value': data.values
        })
        df.set_index('timestamp', inplace=True)
        
        # 应用所有特征转换
        df_features = self._apply_transformations(df)
        
        # 分离特征和目标
        y = df_features['value']
        X = df_features.drop('value', axis=1)
        
        # 删除NaN行
        if self.drop_na:
            valid_mask = ~(X.isna().any(axis=1) | y.isna())
            X = X[valid_mask]
            y = y[valid_mask]
            # logger.debug(f"删除NaN后剩余样本: {len(X)}")
        
        # logger.debug(f"特征转换完成: X={X.shape}, y={y.shape}")
        
        return X, y
    
    def fit_transform(self, data: pd.Series) -> Tuple[pd.DataFrame, pd.Series]:
        """拟合并转换数据
        
        Args:
            data: 时间序列数据
            
        Returns:
            (X, y): 特征矩阵和目标序列
        """
        self.fit(data)
        return self.transform(data)
    
    def _fit_transformers(self, df: pd.DataFrame):
        """初始化并拟合所有转换器
        
        Args:
            df: 数据框（包含 'value' 列）
        """
        # 1. 滞后特征
        if self.lag_periods:
            # logger.debug(f"配置滞后特征: {self.lag_periods}")
            self.lag_transformer = LagFeatures(
                variables=['value'],
                periods=self.lag_periods,
                drop_original=False
            )
            self.lag_transformer.fit(df)
        
        # 2. 滚动窗口特征 - 也在原始数据上fit
        if self.rolling_windows:
            # logger.debug(f"配置滚动窗口特征: windows={self.rolling_windows}, features={self.rolling_features}")
            self.window_transformer = WindowFeatures(
                variables=['value'],
                window=self.rolling_windows,
                functions=self.rolling_features,
                drop_original=False
            )
            # 注意：滚动窗口也要在原始df上fit
            self.window_transformer.fit(df)
        
        # 3. 周期性特征（如果有时间索引）
        if self.use_cyclical_features and isinstance(df.index, pd.DatetimeIndex):
            # logger.debug("配置周期性特征")
            # 提取时间特征用于周期性编码
            df_temp = self._extract_temporal_features(df.copy())
            
            # 选择周期性字段
            cyclical_vars = []
            if 'month' in df_temp.columns:
                cyclical_vars.append('month')
            if 'day_of_week' in df_temp.columns:
                cyclical_vars.append('day_of_week')
            if 'hour' in df_temp.columns:
                cyclical_vars.append('hour')
            
            if cyclical_vars:
                self.cyclical_transformer = CyclicalFeatures(
                    variables=cyclical_vars,
                    drop_original=False
                )
                self.cyclical_transformer.fit(df_temp)
    
    def _apply_transformations(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用所有特征转换
        
        Args:
            df: 原始数据框
            
        Returns:
            包含所有特征的数据框
        """
        df_features = df.copy()
        
        # 1. 滞后特征
        if self.lag_transformer:
            df_features = self.lag_transformer.transform(df_features)
            # logger.debug(f"滞后特征: {len(self.lag_periods)} 个")
        
        # 2. 滚动窗口特征 - 在原始value列上计算
        if self.window_transformer:
            # 创建临时df只包含原始value列用于滚动窗口计算
            df_original_value = df[['value']].copy()
            df_window = self.window_transformer.transform(df_original_value)
            
            # 合并滚动窗口特征到df_features（对齐索引）
            window_cols = [col for col in df_window.columns if col != 'value']
            for col in window_cols:
                df_features[col] = df_window[col]
            
            n_window_features = len(window_cols)
            # logger.debug(f"滚动窗口特征: {n_window_features} 个")
        
        # 3. 时间特征
        if self.use_temporal_features and isinstance(df_features.index, pd.DatetimeIndex):
            df_features = self._extract_temporal_features(df_features)
            # logger.debug("时间特征已提取")
        
        # 4. 周期性特征
        if self.cyclical_transformer:
            df_features = self.cyclical_transformer.transform(df_features)
            # logger.debug("周期性特征已编码")
        
        # 5. 差分特征
        if self.use_diff_features:
            df_features = self._add_diff_features(df_features)
            # logger.debug(f"差分特征: {len(self.diff_periods)} 个")
        
        # 记录特征名
        self.feature_names_ = [col for col in df_features.columns if col != 'value']
        
        return df_features
    
    def _extract_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """提取时间特征
        
        Args:
            df: 数据框（带 DatetimeIndex）
            
        Returns:
            添加了时间特征的数据框
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            return df
        
        # 年月日
        df['year'] = df.index.year
        df['month'] = df.index.month
        df['day'] = df.index.day
        df['day_of_week'] = df.index.dayofweek
        df['day_of_year'] = df.index.dayofyear
        
        # 周、季度
        df['week_of_year'] = df.index.isocalendar().week.astype(int)
        df['quarter'] = df.index.quarter
        
        # 时间（如果有小时信息）
        if hasattr(df.index, 'hour'):
            df['hour'] = df.index.hour
            df['minute'] = df.index.minute
        
        # 是否周末
        df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)
        
        # 月初/月末
        df['is_month_start'] = df.index.is_month_start.astype(int)
        df['is_month_end'] = df.index.is_month_end.astype(int)
        
        # 季节（北半球）
        df['season'] = df['month'].map({
            12: 0, 1: 0, 2: 0,  # 冬
            3: 1, 4: 1, 5: 1,   # 春
            6: 2, 7: 2, 8: 2,   # 夏
            9: 3, 10: 3, 11: 3  # 秋
        })
        
        return df
    
    def _add_diff_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加差分特征
        
        Args:
            df: 数据框
            
        Returns:
            添加了差分特征的数据框
        """
        for period in self.diff_periods:
            col_name = f'value_diff_{period}'
            df[col_name] = df['value'].diff(period)
            # logger.debug(f"添加差分特征: {col_name}")
        
        return df
    
    def get_feature_names(self) -> List[str]:
        """获取所有特征名称
        
        Returns:
            特征名称列表
        """
        if not self.is_fitted:
            raise RuntimeError("必须先调用 fit() 方法")
        
        return self.feature_names_.copy()
    
    def get_feature_importance_map(self, importance_values: np.ndarray) -> Dict[str, float]:
        """将特征重要性值映射到特征名
        
        Args:
            importance_values: 特征重要性数组
            
        Returns:
            特征名 -> 重要性的字典
        """
        if not self.is_fitted:
            raise RuntimeError("必须先调用 fit() 方法")
        
        if len(importance_values) != len(self.feature_names_):
            raise ValueError(
                f"重要性数组长度({len(importance_values)})与特征数({len(self.feature_names_)})不匹配"
            )
        
        return dict(zip(self.feature_names_, importance_values))
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置信息
        
        Returns:
            配置字典
        """
        return {
            'lag_periods': self.lag_periods,
            'rolling_windows': self.rolling_windows,
            'rolling_features': self.rolling_features,
            'use_temporal_features': self.use_temporal_features,
            'use_cyclical_features': self.use_cyclical_features,
            'use_diff_features': self.use_diff_features,
            'diff_periods': self.diff_periods,
            'seasonal_period': self.seasonal_period,
            'drop_na': self.drop_na
        }
    
    def __repr__(self) -> str:
        status = "fitted" if self.is_fitted else "not fitted"
        n_features = len(self.feature_names_) if self.is_fitted else 0
        return (
            f"TimeSeriesFeatureEngineer(status={status}, "
            f"n_features={n_features}, "
            f"lag_periods={len(self.lag_periods)}, "
            f"rolling_windows={len(self.rolling_windows)})"
        )


class FeatureSelector:
    """特征选择器
    
    基于重要性或相关性筛选最重要的特征。
    """
    
    def __init__(
        self,
        method: str = 'importance',
        n_features: Optional[int] = None,
        threshold: Optional[float] = None
    ):
        """初始化特征选择器
        
        Args:
            method: 选择方法 ('importance', 'correlation', 'variance')
            n_features: 保留的特征数量
            threshold: 重要性/相关性阈值
        """
        self.method = method
        self.n_features = n_features
        self.threshold = threshold
        self.selected_features_ = []
        self.is_fitted = False
    
    def fit(self, X: pd.DataFrame, y: pd.Series, feature_importance: Optional[np.ndarray] = None):
        """拟合特征选择器
        
        Args:
            X: 特征矩阵
            y: 目标变量
            feature_importance: 特征重要性（用于 'importance' 方法）
        """
        if self.method == 'importance':
            if feature_importance is None:
                raise ValueError("method='importance' 需要提供 feature_importance")
            
            self._select_by_importance(X, feature_importance)
        
        elif self.method == 'correlation':
            self._select_by_correlation(X, y)
        
        elif self.method == 'variance':
            self._select_by_variance(X)
        
        else:
            raise ValueError(f"不支持的方法: {self.method}")
        
        self.is_fitted = True
        logger.info(f"特征选择完成，选中 {len(self.selected_features_)} 个特征")
        
        return self
    
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """转换特征矩阵
        
        Args:
            X: 特征矩阵
            
        Returns:
            筛选后的特征矩阵
        """
        if not self.is_fitted:
            raise RuntimeError("必须先调用 fit() 方法")
        
        return X[self.selected_features_]
    
    def _select_by_importance(self, X: pd.DataFrame, importance: np.ndarray):
        """基于重要性选择特征"""
        importance_df = pd.DataFrame({
            'feature': X.columns,
            'importance': importance
        }).sort_values('importance', ascending=False)
        
        if self.n_features:
            self.selected_features_ = importance_df.head(self.n_features)['feature'].tolist()
        elif self.threshold:
            self.selected_features_ = importance_df[
                importance_df['importance'] >= self.threshold
            ]['feature'].tolist()
        else:
            self.selected_features_ = X.columns.tolist()
    
    def _select_by_correlation(self, X: pd.DataFrame, y: pd.Series):
        """基于与目标变量的相关性选择特征"""
        correlations = X.corrwith(y).abs().sort_values(ascending=False)
        
        if self.n_features:
            self.selected_features_ = correlations.head(self.n_features).index.tolist()
        elif self.threshold:
            self.selected_features_ = correlations[correlations >= self.threshold].index.tolist()
        else:
            self.selected_features_ = X.columns.tolist()
    
    def _select_by_variance(self, X: pd.DataFrame):
        """基于方差选择特征"""
        variances = X.var().sort_values(ascending=False)
        
        if self.n_features:
            self.selected_features_ = variances.head(self.n_features).index.tolist()
        elif self.threshold:
            self.selected_features_ = variances[variances >= self.threshold].index.tolist()
        else:
            self.selected_features_ = X.columns.tolist()
