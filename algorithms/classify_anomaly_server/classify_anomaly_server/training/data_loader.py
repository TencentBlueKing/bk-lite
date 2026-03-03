"""数据加载模块 - 异常检测."""

from pathlib import Path
from typing import Tuple, Optional
import pandas as pd
from loguru import logger


def load_dataset(
    dataset_path: str,
    label_column: Optional[str] = None
) -> pd.DataFrame:
    """
    加载异常检测数据集.
    
    支持的格式:
    - CSV 文件: 必须包含 'date'/'timestamp' 和 'value' 列
    - 可选包含标签列（用于有监督评估）
    
    Args:
        dataset_path: 数据集文件路径
        label_column: 标签列名（可选），如 'label', 'is_anomaly', 'anomaly'
        
    Returns:
        包含时间序列数据的 DataFrame（标准化后包含 date, value, 可选 label 列）
        
    Raises:
        FileNotFoundError: 数据集路径不存在
        ValueError: 数据格式不正确
    """
    path = Path(dataset_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
    
    # 加载文件
    if path.is_file():
        if path.suffix.lower() in ['.csv', '.txt']:
            logger.info(f"加载 CSV 文件: {path}")
            df = pd.read_csv(path)
        elif path.suffix.lower() == '.parquet':
            logger.info(f"加载 Parquet 文件: {path}")
            df = pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")
    else:
        raise ValueError(f"Path must be a file, got directory: {path}")
    
    logger.info(f"已加载数据集，形状: {df.shape}")
    logger.info(f"列名: {df.columns.tolist()}")
    
    # 验证和标准化列名
    df, has_labels = _standardize_columns(df, label_column)
    
    logger.info("数据集加载成功")
    logger.info(f"数据点: {len(df)}")
    
    if 'date' in df.columns:
        # 确保 date 列是 datetime 类型
        if not pd.api.types.is_datetime64_any_dtype(df['date']):
            df['date'] = pd.to_datetime(df['date'])
        
        logger.info(f"日期范围: {df['date'].min()} 至 {df['date'].max()}")
    
    logger.info(f"数值统计: 最小值={df['value'].min():.2f}, 最大值={df['value'].max():.2f}, 平均值={df['value'].mean():.2f}")
    
    if has_labels:
        anomaly_count = df[label_column or 'label'].sum()
        anomaly_ratio = anomaly_count / len(df) * 100
        logger.info(f"异常样本: {int(anomaly_count)} ({anomaly_ratio:.2f}%)")
    
    return df


def _standardize_columns(
    df: pd.DataFrame,
    label_column: Optional[str] = None
) -> Tuple[pd.DataFrame, bool]:
    """标准化列名
    
    Args:
        df: 原始数据框
        label_column: 指定的标签列名
        
    Returns:
        (标准化后的DataFrame, 是否有标签)
    """
    df = df.copy()
    has_labels = False
    
    # 1. 标准化时间列
    if 'timestamp' in df.columns and 'date' not in df.columns:
        df['date'] = df['timestamp']
        df = df.drop(columns=['timestamp'])
    elif 'time' in df.columns and 'date' not in df.columns:
        df['date'] = df['time']
        df = df.drop(columns=['time'])
    
    if 'date' not in df.columns:
        # 尝试找到日期相关的列
        date_like_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
        if date_like_cols:
            df['date'] = df[date_like_cols[0]]
            logger.info(f"使用列 '{date_like_cols[0]}' 作为时间列")
        else:
            logger.warning("未找到时间列，使用索引作为时间")
            df['date'] = pd.date_range(start='2020-01-01', periods=len(df), freq='H')
    
    # 2. 标准化数值列
    if 'value' not in df.columns:
        # 尝试找到数值列
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        # 排除可能是标签的列
        label_like = ['label', 'anomaly', 'is_anomaly', 'target', 'y']
        numeric_cols = [col for col in numeric_cols if col.lower() not in label_like]
        
        if len(numeric_cols) == 0:
            raise ValueError("No numeric columns found for 'value'")
        
        df['value'] = df[numeric_cols[0]]
        logger.info(f"使用列 '{numeric_cols[0]}' 作为数值列")
    
    # 3. 标准化标签列
    if label_column:
        if label_column in df.columns:
            has_labels = True
            logger.info(f"使用标签列: {label_column}")
        else:
            logger.warning(f"指定的标签列 '{label_column}' 不存在")
    else:
        # 自动检测标签列
        label_candidates = ['label', 'is_anomaly', 'anomaly', 'target', 'y']
        for col in label_candidates:
            if col in df.columns:
                label_column = col
                has_labels = True
                logger.info(f"自动检测到标签列: {col}")
                break
    
    # 4. 只保留需要的列
    keep_cols = ['date', 'value']
    if has_labels and label_column:
        keep_cols.append(label_column)
    
    # 删除其他列
    df = df[keep_cols]
    
    return df, has_labels


def split_train_test(
    df: pd.DataFrame,
    test_ratio: float = 0.2
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """分割训练集和测试集
    
    Args:
        df: 数据框
        test_ratio: 测试集比例
        
    Returns:
        (train_df, test_df)
    """
    split_idx = int(len(df) * (1 - test_ratio))
    
    train_df = df.iloc[:split_idx].copy()
    test_df = df.iloc[split_idx:].copy()
    
    logger.info(f"数据集分割: 训练集={len(train_df)}, 测试集={len(test_df)}")
    
    if 'label' in df.columns:
        train_anomalies = train_df['label'].sum()
        test_anomalies = test_df['label'].sum()
        logger.info(f"训练集异常: {int(train_anomalies)}, 测试集异常: {int(test_anomalies)}")
    
    return train_df, test_df
