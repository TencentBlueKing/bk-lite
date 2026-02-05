"""数据加载模块"""
from pathlib import Path
from typing import Tuple, Optional
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from loguru import logger


def load_csv_dataset(file_path: str) -> pd.DataFrame:
    """加载 CSV 数据集
    
    Args:
        file_path: CSV 文件路径
        
    Returns:
        包含 text 和 label 列的 DataFrame
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 缺少必需的列
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"数据集文件不存在: {file_path}")
    
    logger.info(f"📁 加载数据集: {file_path}")
    df = pd.read_csv(file_path)
    
    # 检查必需的列
    required_columns = ["text", "label"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        raise ValueError(f"数据集缺少必需的列: {missing_columns}. "
                        f"当前列: {df.columns.tolist()}")
    
    logger.info(f"数据集加载完成: {len(df)} 条样本, "
               f"列: {df.columns.tolist()}")
    
    # 移除缺失值
    original_len = len(df)
    df = df.dropna(subset=["text", "label"])
    if len(df) < original_len:
        logger.warning(f"⚠ 移除了 {original_len - len(df)} 条包含缺失值的样本")
    
    return df


def split_dataset(
    df: pd.DataFrame,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """分割数据集为训练集、验证集、测试集
    
    Args:
        df: 原始数据集
        train_ratio: 训练集比例
        val_ratio: 验证集比例
        test_ratio: 测试集比例
        random_state: 随机种子
        
    Returns:
        (train_df, val_df, test_df) 元组
        
    Raises:
        ValueError: 比例和不为1
    """
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
        raise ValueError(f"数据集比例之和必须为1，当前: "
                        f"{train_ratio} + {val_ratio} + {test_ratio} = "
                        f"{train_ratio + val_ratio + test_ratio}")
    
    logger.info(f"📊 分割数据集: train={train_ratio}, val={val_ratio}, test={test_ratio}")
    
    # 第一次分割：分离出训练集
    train_df, temp_df = train_test_split(
        df,
        train_size=train_ratio,
        random_state=random_state,
        stratify=df["label"]  # 保持类别分布
    )
    
    # 第二次分割：从剩余数据中分离验证集和测试集
    val_size_adjusted = val_ratio / (val_ratio + test_ratio)
    val_df, test_df = train_test_split(
        temp_df,
        train_size=val_size_adjusted,
        random_state=random_state,
        stratify=temp_df["label"]
    )
    
    logger.info(f"数据集分割完成: "
               f"train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")
    
    # 显示类别分布
    logger.info(f"训练集类别分布:\n{train_df['label'].value_counts()}")
    logger.info(f"验证集类别分布:\n{val_df['label'].value_counts()}")
    logger.info(f"测试集类别分布:\n{test_df['label'].value_counts()}")
    
    return train_df, val_df, test_df


def load_and_split(
    dataset_path: str,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """加载并分割数据集
    
    支持两种模式：
    1. 单文件模式：传入 CSV 文件路径，自动分割
    2. 目录模式：传入目录路径，加载 train.csv, val.csv, test.csv
    
    Args:
        dataset_path: 数据集文件或目录路径
        train_ratio: 训练集比例（仅单文件模式）
        val_ratio: 验证集比例（仅单文件模式）
        test_ratio: 测试集比例（仅单文件模式）
        random_state: 随机种子
        
    Returns:
        (train_df, val_df, test_df) 元组
    """
    dataset_path = Path(dataset_path)
    
    # 目录模式
    if dataset_path.is_dir():
        logger.info(f"📁 检测到目录模式: {dataset_path}")
        
        # 支持多种文件命名格式
        train_file = dataset_path / "train_data.csv" if (dataset_path / "train_data.csv").exists() else dataset_path / "train.csv"
        val_file = dataset_path / "val_data.csv" if (dataset_path / "val_data.csv").exists() else dataset_path / "val.csv"
        test_file = dataset_path / "test_data.csv" if (dataset_path / "test_data.csv").exists() else dataset_path / "test.csv"
        
        if not train_file.exists():
            raise FileNotFoundError(f"训练集文件不存在: {train_file}. "
                                   f"请确保目录下存在 train.csv 或 train_data.csv")
        
        train_df = load_csv_dataset(str(train_file))
        
        # 验证集和测试集可选
        val_df = load_csv_dataset(str(val_file)) if val_file.exists() else None
        test_df = load_csv_dataset(str(test_file)) if test_file.exists() else None
        
        if val_df is None:
            logger.warning("⚠ 未找到 val_data.csv，将从训练集自动划分")
            train_df, val_df = train_test_split(
                train_df,
                train_size=0.85,
                random_state=random_state,
                stratify=train_df["label"]
            )
        
        if test_df is None:
            logger.warning("⚠ 未找到 test_data.csv，将从训练集自动划分")
            test_df = val_df
        
        return train_df, val_df, test_df
    
    # 单文件模式
    elif dataset_path.is_file():
        logger.info(f"📄 检测到文件模式: {dataset_path}")
        logger.info("ℹ 将按固定比例自动划分（train=0.7, val=0.15, test=0.15）")
        df = load_csv_dataset(str(dataset_path))
        return split_dataset(df, train_ratio, val_ratio, test_ratio, random_state)
    
    else:
        raise FileNotFoundError(f"数据集路径不存在: {dataset_path}")


def encode_labels(
    train_labels: pd.Series,
    val_labels: Optional[pd.Series] = None,
    test_labels: Optional[pd.Series] = None
) -> Tuple[pd.Series, Optional[pd.Series], Optional[pd.Series], LabelEncoder]:
    """编码标签为整数
    
    Args:
        train_labels: 训练集标签
        val_labels: 验证集标签
        test_labels: 测试集标签
        
    Returns:
        (train_encoded, val_encoded, test_encoded, label_encoder) 元组
    """
    logger.info(f"编码标签，类别数: {train_labels.nunique()}")
    
    label_encoder = LabelEncoder()
    train_encoded = pd.Series(label_encoder.fit_transform(train_labels))
    
    val_encoded = None
    if val_labels is not None:
        val_encoded = pd.Series(label_encoder.transform(val_labels))
    
    test_encoded = None
    if test_labels is not None:
        test_encoded = pd.Series(label_encoder.transform(test_labels))
    
    # 显示标签映射
    label_mapping = dict(zip(label_encoder.classes_, label_encoder.transform(label_encoder.classes_)))
    logger.info(f"标签映射: {label_mapping}")
    
    return train_encoded, val_encoded, test_encoded, label_encoder
