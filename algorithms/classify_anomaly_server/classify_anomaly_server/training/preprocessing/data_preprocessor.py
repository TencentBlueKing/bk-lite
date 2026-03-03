"""异常检测数据预处理器

提供异常检测数据的清洗和预处理功能。
"""

from typing import Optional, Tuple
import pandas as pd
import numpy as np
from loguru import logger


class AnomalyDataPreprocessor:
    """异常检测数据预处理器
    
    核心功能：
    1. 时间列标准化和排序
    2. 时间频率推断
    3. 缺失值处理
    4. 数据质量检查
    5. 标签处理（如果有）
    
    与时间序列预测的差异：
    - 支持可选的标签列处理
    - 更宽松的数据要求（可以不是完整的时间序列）
    - 关注异常样本的保留
    """
    
    def __init__(self, 
                 max_missing_ratio: float = 0.3,
                 handle_missing: str = "interpolate"):
        """初始化预处理器
        
        Args:
            max_missing_ratio: 允许的最大缺失率，超过则报错
            handle_missing: 缺失值处理方法
                - "interpolate": 时间插值（推荐）
                - "ffill": 前向填充
                - "bfill": 后向填充
                - "median": 中位数填充
                - "drop": 删除缺失值
        """
        self.max_missing_ratio = max_missing_ratio
        self.handle_missing = handle_missing
        
        logger.debug(
            f"预处理器初始化: max_missing_ratio={max_missing_ratio}, "
            f"handle_missing={handle_missing}"
        )
    
    def clean(self, 
              df: pd.DataFrame,
              label_column: Optional[str] = None) -> Tuple[pd.DataFrame, Optional[str]]:
        """清洗异常检测数据
        
        Args:
            df: 原始数据框，必须包含 'date' 和 'value' 列
            label_column: 标签列名（可选），如 'label' 或 'is_anomaly'
            
        Returns:
            (清洗后的DataFrame, 推断的频率)
            - DataFrame: 带 DatetimeIndex，包含 value 列和可选的 label 列
            - frequency: 推断的时间频率字符串
            
        Raises:
            ValueError: 数据格式不正确或质量不足
        """
        if df is None or df.empty:
            raise ValueError("输入数据为空")
        
        logger.info("开始数据清洗...")
        
        df = df.copy()
        
        # 1. 验证必需列
        self._validate_columns(df, label_column)
        
        # 2. 时间列标准化
        df = self._standardize_datetime(df)
        
        # 3. 排序和去重
        df = self._sort_and_deduplicate(df)
        
        # 4. 处理标签列（如果有）
        if label_column and label_column in df.columns:
            df = self._process_labels(df, label_column)
        
        # 5. 设置时间索引
        df = df.set_index("date")
        
        # 6. 推断频率
        inferred_freq = self._infer_frequency(df)
        
        # 7. 缺失值处理
        df = self._handle_missing_values(df)
        
        logger.info(
            f"数据清洗完成 - 数据点: {len(df)}, "
            f"频率: {inferred_freq or '未知'}"
        )
        
        if label_column and label_column in df.columns:
            anomaly_count = df[label_column].sum()
            anomaly_ratio = anomaly_count / len(df) * 100
            logger.info(f"异常样本: {int(anomaly_count)} ({anomaly_ratio:.2f}%)")
        
        return df, inferred_freq
    
    def _validate_columns(self, df: pd.DataFrame, label_column: Optional[str] = None):
        """验证必需的列"""
        if 'date' not in df.columns and 'timestamp' not in df.columns:
            raise ValueError("DataFrame 必须包含 'date' 或 'timestamp' 列")
        
        if 'value' not in df.columns:
            raise ValueError("DataFrame 必须包含 'value' 列")
        
        if label_column and label_column not in df.columns:
            raise ValueError(f"指定的标签列 '{label_column}' 不存在")
    
    def _standardize_datetime(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化时间列"""
        # 统一使用 'date' 列名
        if 'timestamp' in df.columns and 'date' not in df.columns:
            df['date'] = df['timestamp']
        
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
    
    def _process_labels(self, df: pd.DataFrame, label_column: str) -> pd.DataFrame:
        """处理标签列
        
        Args:
            df: 数据框
            label_column: 标签列名
            
        Returns:
            处理后的数据框，标签统一为 'label' 列（0=正常, 1=异常）
        """
        logger.debug(f"处理标签列: {label_column}")
        
        # 重命名为标准列名
        if label_column != 'label':
            df['label'] = df[label_column]
            df = df.drop(columns=[label_column])
        
        # 确保标签是 0/1 格式
        unique_labels = df['label'].unique()
        
        # 如果是布尔型，转换为 0/1
        if df['label'].dtype == bool:
            df['label'] = df['label'].astype(int)
        
        # 如果不是 0/1，尝试映射
        elif not set(unique_labels).issubset({0, 1}):
            logger.warning(f"标签值不是 0/1: {unique_labels}，尝试自动映射...")
            
            # 假设最常见的值是正常（0），其他是异常（1）
            most_common = df['label'].value_counts().idxmax()
            df['label'] = (df['label'] != most_common).astype(int)
            
            logger.info(f"标签映射: {most_common} -> 0 (正常), 其他 -> 1 (异常)")
        
        # 处理缺失值（假设缺失=正常）
        if df['label'].isna().any():
            missing_count = df['label'].isna().sum()
            logger.warning(f"标签缺失 {missing_count} 个，填充为 0 (正常)")
            df['label'] = df['label'].fillna(0).astype(int)
        
        return df
    
    def _infer_frequency(self, df: pd.DataFrame) -> Optional[str]:
        """推断时间频率"""
        try:
            inferred_freq = pd.infer_freq(df.index)
            if inferred_freq:
                logger.debug(f"推断时间频率: {inferred_freq}")
                return inferred_freq
        except Exception as e:
            logger.debug(f"无法推断时间频率: {e}")
        
        # 尝试计算中位数时间间隔
        if len(df) > 1:
            time_diffs = df.index.to_series().diff().dropna()
            median_diff = time_diffs.median()
            logger.debug(f"中位数时间间隔: {median_diff}")
            
            # 转换为频率字符串
            if median_diff == pd.Timedelta(days=1):
                return 'D'
            elif median_diff == pd.Timedelta(hours=1):
                return 'H'
            elif median_diff == pd.Timedelta(minutes=5):
                return '5min'
            elif median_diff == pd.Timedelta(minutes=1):
                return 'T'
        
        return None
    
    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """处理缺失值"""
        missing_count = df['value'].isna().sum()
        
        if missing_count == 0:
            return df
        
        missing_ratio = missing_count / len(df)
        logger.warning(f"发现 {missing_count} 个缺失值 ({missing_ratio:.1%})")
        
        # 检查缺失率
        if missing_ratio > self.max_missing_ratio:
            raise ValueError(
                f"缺失率 ({missing_ratio:.1%}) 超过阈值 ({self.max_missing_ratio:.1%})"
            )
        
        # 根据策略处理
        if self.handle_missing == "interpolate":
            df['value'] = df['value'].interpolate(method='time', limit_direction='both')
        elif self.handle_missing == "ffill":
            df['value'] = df['value'].fillna(method='ffill')
        elif self.handle_missing == "bfill":
            df['value'] = df['value'].fillna(method='bfill')
        elif self.handle_missing == "median":
            median_value = df['value'].median()
            df['value'] = df['value'].fillna(median_value)
        elif self.handle_missing == "drop":
            df = df.dropna(subset=['value'])
        else:
            raise ValueError(f"Unknown missing handling method: {self.handle_missing}")
        
        # 再次检查
        remaining_missing = df['value'].isna().sum()
        if remaining_missing > 0:
            logger.warning(f"仍有 {remaining_missing} 个缺失值，删除这些行")
            df = df.dropna(subset=['value'])
        
        return df
