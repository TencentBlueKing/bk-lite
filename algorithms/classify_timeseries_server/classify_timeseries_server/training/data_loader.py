"""数据加载模块."""

from pathlib import Path
import pandas as pd
from loguru import logger


def load_dataset(dataset_path: str) -> pd.DataFrame:
    """
    加载时间序列数据集.
    
    支持的格式:
    - CSV 文件: 必须包含 'date' 和 'value' 列
    - CSV 文件夹: 加载所有 CSV 文件并合并
    
    Args:
        dataset_path: 数据集文件或文件夹路径
        
    Returns:
        包含时间序列数据的 DataFrame
        
    Raises:
        FileNotFoundError: 数据集路径不存在
        ValueError: 数据格式不正确
    """
    path = Path(dataset_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path}")
    
    # 如果是文件
    if path.is_file():
        if path.suffix.lower() in ['.csv', '.txt']:
            logger.info(f"加载 CSV 文件: {path}")
            df = pd.read_csv(path)
        elif path.suffix.lower() == '.parquet':
            logger.info(f"加载 Parquet 文件: {path}")
            df = pd.read_parquet(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")
    
    # 如果是文件夹，加载所有 CSV 文件
    else:
        logger.info(f"从目录加载 CSV 文件: {path}")
        csv_files = list(path.glob("*.csv"))
        
        if not csv_files:
            raise FileNotFoundError(f"No CSV files found in: {path}")
        
        logger.info(f"找到 {len(csv_files)} 个 CSV 文件")
        dfs = []
        for csv_file in csv_files:
            logger.debug(f"读取 {csv_file.name}")
            dfs.append(pd.read_csv(csv_file))
        
        df = pd.concat(dfs, ignore_index=True)
    
    logger.info(f"已加载数据集，形状: {df.shape}")
    logger.info(f"列名: {df.columns.tolist()}")
    
    # 验证必需的列
    if 'date' not in df.columns and 'timestamp' not in df.columns:
        logger.warning("未找到 'date' 或 'timestamp' 列，使用索引作为日期")
        df['date'] = pd.date_range(start='2020-01-01', periods=len(df), freq='D')
    
    if 'value' not in df.columns:
        # 尝试找到数值列
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) == 0:
            raise ValueError("No numeric columns found in dataset")
        
        logger.warning(f"未找到 'value' 列，使用第一个数值列: {numeric_cols[0]}")
        df['value'] = df[numeric_cols[0]]
    
    # 标准化日期列名
    if 'timestamp' in df.columns:
        df['date'] = df['timestamp']
    
    # 转换日期列为 datetime
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])
    
    # 按日期排序
    df = df.sort_values('date').reset_index(drop=True)
    
    logger.info("数据集加载成功")
    logger.info(f"日期范围: {df['date'].min()} 至 {df['date'].max()}")
    logger.info(f"数值统计: 最小值={df['value'].min():.2f}, 最大值={df['value'].max():.2f}, 平均值={df['value'].mean():.2f}")
    
    return df
