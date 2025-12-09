"""时间序列数据预处理器

从 sarima_trainer.preprocess() 提取并增强的预处理逻辑。
"""

from typing import Optional, Tuple
import pandas as pd
import numpy as np
from loguru import logger


class TimeSeriesPreprocessor:
    """时间序列专用预处理器
    
    核心功能：
    1. 时间列标准化和排序
    2. 时间频率推断
    3. 缺失值处理（时间序列友好）
    4. 数据质量检查
    
    原则：
    - 最小干预：只处理必要的数据质量问题
    - 保留异常：不削平极值（SARIMA 有鲁棒性）
    - 尊重时间：使用前向填充，不用全局统计
    """
    
    def __init__(self, 
                 max_missing_ratio: float = 0.3,
                 interpolation_limit: int = 3,
                 handle_missing: str = "interpolate"):
        """初始化预处理器
        
        Args:
            max_missing_ratio: 允许的最大缺失率，超过则报错
            interpolation_limit: 插值最多填充的连续缺失点数
            handle_missing: 缺失值处理方法
                - "interpolate": 时间插值（推荐）
                - "ffill": 前向填充
                - "bfill": 后向填充
                - "median": 中位数填充
        """
        self.max_missing_ratio = max_missing_ratio
        self.interpolation_limit = interpolation_limit
        self.handle_missing = handle_missing
        
        logger.debug(
            f"预处理器初始化: max_missing_ratio={max_missing_ratio}, "
            f"interpolation_limit={interpolation_limit}, "
            f"handle_missing={handle_missing}"
        )
    
    def preprocess(
        self, 
        df: pd.DataFrame, 
        frequency: Optional[str] = None
    ) -> Tuple[pd.DataFrame, Optional[str]]:
        """完整的数据预处理流程
        
        Args:
            df: 原始数据框，必须包含 'date' 和 'value' 列
            frequency: 时间频率（'5min', 'H', 'D' 等），None 则自动推断
            
        Returns:
            (处理后的DataFrame, 推断的频率)
            
        Raises:
            ValueError: 数据格式不正确或质量不足
        """
        if df is None or df.empty:
            raise ValueError("输入数据为空")
        
        logger.info("开始数据预处理...")
        
        df = df.copy()
        
        # 1. 验证必需列
        self._validate_columns(df)
        
        # 2. 时间列标准化
        df = self._standardize_datetime(df)
        
        # 3. 排序和去重
        df = self._sort_and_deduplicate(df)
        
        # 4. 设置时间索引，推断频率
        df = df.set_index("date")
        frequency = self._infer_frequency(df, frequency)
        
        # 5. 缺失值处理
        df = self._handle_missing_values(df)
        
        # 6. 重置索引（返回 date 列）
        df = df.reset_index()
        
        logger.info(f"预处理完成 - 数据点: {len(df)}, 频率: {frequency or '未知'}")
        
        return df, frequency
    
    def _validate_columns(self, df: pd.DataFrame):
        """验证必需的列"""
        if 'date' not in df.columns:
            raise ValueError("DataFrame 必须包含 'date' 列")
        
        if 'value' not in df.columns:
            raise ValueError("DataFrame 必须包含 'value' 列")
    
    def _standardize_datetime(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化时间列"""
        if not np.issubdtype(df["date"].dtype, np.datetime64):
            logger.debug("转换 date 列为 datetime 类型")
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        
        # 移除无效时间
        invalid_dates = df["date"].isna().sum()
        if invalid_dates > 0:
            logger.warning(f"移除 {invalid_dates} 个无效时间戳")
            df = df.dropna(subset=["date"])
        
        if len(df) == 0:
            raise ValueError("所有时间戳都无效，无法处理")
        
        return df
    
    def _sort_and_deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """排序并去重"""
        original_len = len(df)
        
        # 排序
        df = df.sort_values("date")
        
        # 去重（保留最后一条）
        df = df.drop_duplicates(subset=['date'], keep='last')
        
        duplicates = original_len - len(df)
        if duplicates > 0:
            logger.warning(f"移除 {duplicates} 个重复时间戳")
        
        return df
    
    def _infer_frequency(self, df: pd.DataFrame, frequency: Optional[str]) -> Optional[str]:
        """推断或验证时间频率"""
        if frequency is not None:
            logger.info(f"使用指定频率: {frequency}")
            return frequency
        
        try:
            inferred_freq = pd.infer_freq(df.index)
            if inferred_freq:
                logger.info(f"推断频率: {inferred_freq}")
                return inferred_freq
            else:
                logger.warning("无法推断频率，数据可能不规则")
                return None
        except Exception as e:
            logger.warning(f"频率推断失败: {e}")
            return None
    
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值（时间序列友好）
        
        策略优先级：
        1. 检查缺失率，超过阈值则报错
        2. 根据 handle_missing 方法进行填充
        3. 最后保障：用中位数填充剩余缺失
        """
        value_series = df["value"].astype(float)
        missing_count = value_series.isna().sum()
        missing_ratio = missing_count / len(value_series)
        
        # 检查缺失率
        if missing_ratio > self.max_missing_ratio:
            raise ValueError(
                f"数据质量不足: 缺失率 {missing_ratio:.2%} 超过阈值 "
                f"{self.max_missing_ratio:.2%}"
            )
        
        if missing_count == 0:
            logger.debug("无缺失值")
            df["value"] = value_series
            return df
        
        logger.info(f"发现 {missing_count} 个缺失值 ({missing_ratio:.2%})")
        
        # 根据策略填充
        if self.handle_missing == "interpolate":
            value_series = self._interpolate_missing(value_series)
        elif self.handle_missing == "ffill":
            value_series = value_series.ffill()
        elif self.handle_missing == "bfill":
            value_series = value_series.bfill()
        elif self.handle_missing == "median":
            median_value = value_series.median()
            value_series = value_series.fillna(median_value)
            logger.info(f"用中位数 {median_value:.4f} 填充缺失值")
        else:
            logger.warning(f"未知的填充方法: {self.handle_missing}，使用默认插值")
            value_series = self._interpolate_missing(value_series)
        
        # 最后保障：前后向填充
        value_series = value_series.ffill().bfill()
        
        # 如果仍有缺失（极端情况），用中位数
        remaining_na = value_series.isna().sum()
        if remaining_na > 0:
            median_value = value_series.median()
            if np.isnan(median_value):
                median_value = 0.0
            value_series = value_series.fillna(median_value)
            logger.warning(f"用中位数 {median_value:.4f} 填充剩余 {remaining_na} 个缺失值")
        
        df["value"] = value_series
        return df
    
    def _interpolate_missing(self, series: pd.Series) -> pd.Series:
        """时间插值填充
        
        Args:
            series: 待填充的序列
            
        Returns:
            填充后的序列
        """
        # 时间加权插值
        series = series.interpolate(
            method="time",
            limit=self.interpolation_limit,
            limit_direction="both"
        )
        
        # 前向填充（处理起始缺失）
        series = series.ffill(limit=self.interpolation_limit * 2)
        
        # 后向填充（处理末尾缺失）
        series = series.bfill(limit=self.interpolation_limit * 2)
        
        return series
    
    def get_data_summary(self, df: pd.DataFrame) -> dict:
        """获取数据摘要信息
        
        Args:
            df: 数据框
            
        Returns:
            数据摘要字典
        """
        if 'value' not in df.columns:
            return {}
        
        values = df['value'].astype(float)
        
        return {
            'length': len(df),
            'missing_count': values.isna().sum(),
            'missing_ratio': values.isna().sum() / len(values),
            'mean': float(values.mean()),
            'std': float(values.std()),
            'min': float(values.min()),
            'max': float(values.max()),
            'median': float(values.median()),
        }
