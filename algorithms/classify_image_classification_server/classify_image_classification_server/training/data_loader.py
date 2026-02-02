"""数据加载器 - ImageFolder格式."""

from typing import Tuple, List, Optional
from pathlib import Path
from loguru import logger
from PIL import Image
import os


class DataLoadError(Exception):
    """数据加载错误异常."""
    pass


def load_dataset(dataset_path: str) -> Tuple[Tuple[str, List[str]], Optional[Tuple[str, List[str]]], Optional[Tuple[str, List[str]]]]:
    """
    加载ImageFolder格式的图片分类数据集.
    
    数据集结构应为:
    dataset_path/
    ├── train/
    │   ├── class1/
    │   │   ├── img1.jpg
    │   │   └── img2.jpg
    │   ├── class2/
    │   │   └── img3.jpg
    ├── val/  (可选)
    │   ├── class1/
    │   └── class2/
    └── test/  (可选)
        ├── class1/
        └── class2/
    
    Args:
        dataset_path: 数据集根目录路径
        
    Returns:
        (train_data, val_data, test_data)
        - train_data: (train_path, class_names)
        - val_data: (val_path, class_names) or None
        - test_data: (test_path, class_names) or None
        
    Raises:
        DataLoadError: 数据集格式错误或不存在
    """
    dataset_path = Path(dataset_path)
    
    if not dataset_path.exists():
        raise DataLoadError(f"数据集路径不存在: {dataset_path}")
    
    if not dataset_path.is_dir():
        raise DataLoadError(f"数据集路径必须是目录: {dataset_path}")
    
    # 检查train目录（必需）
    train_path = dataset_path / "train"
    if not train_path.exists():
        raise DataLoadError(
            f"训练集目录不存在: {train_path}\n"
            f"数据集必须包含train/目录"
        )
    
    # 获取类别名称（从train目录）
    class_names = get_class_names(train_path)
    if len(class_names) == 0:
        raise DataLoadError(f"训练集中未找到类别目录: {train_path}")
    
    logger.info(f"检测到{len(class_names)}个类别: {class_names}")
    
    # 验证训练集
    validate_image_folder(train_path, class_names)
    train_data = (str(train_path), class_names)
    
    # 检查val目录（可选）
    val_path = dataset_path / "val"
    val_data = None
    if val_path.exists():
        validate_image_folder(val_path, class_names)
        val_data = (str(val_path), class_names)
        logger.info(f"验证集目录存在: {val_path}")
    else:
        logger.info("未找到验证集目录，训练时将不使用验证集")
    
    # 检查test目录（可选）
    test_path = dataset_path / "test"
    test_data = None
    if test_path.exists():
        validate_image_folder(test_path, class_names)
        test_data = (str(test_path), class_names)
        logger.info(f"测试集目录存在: {test_path}")
    else:
        logger.info("未找到测试集目录，训练完成后将不进行测试评估")
    
    return train_data, val_data, test_data


def get_class_names(data_path: Path) -> List[str]:
    """
    从目录中提取类别名称.
    
    Args:
        data_path: 数据目录路径
        
    Returns:
        排序后的类别名称列表
    """
    if not data_path.exists():
        return []
    
    class_names = []
    for item in data_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            class_names.append(item.name)
    
    return sorted(class_names)


def validate_image_folder(data_path: Path, class_names: List[str]):
    """
    验证ImageFolder目录结构和内容.
    
    Args:
        data_path: 数据目录路径
        class_names: 期望的类别名称列表
        
    Raises:
        DataLoadError: 目录结构或内容不合法
    """
    if not data_path.exists():
        raise DataLoadError(f"目录不存在: {data_path}")
    
    # 检查每个类别目录
    for class_name in class_names:
        class_dir = data_path / class_name
        if not class_dir.exists():
            logger.warning(f"类别目录不存在: {class_dir}")
            continue
        
        if not class_dir.is_dir():
            raise DataLoadError(f"类别路径不是目录: {class_dir}")
        
        # 检查是否有图片文件
        image_files = list_image_files(class_dir)
        if len(image_files) == 0:
            logger.warning(f"类别目录为空: {class_dir}")
    
    # 获取数据集统计信息
    stats = get_dataset_stats(data_path, class_names)
    logger.info(
        f"数据集验证通过: {data_path.name}目录 - "
        f"总图片数={stats['total_images']}, "
        f"类别数={stats['num_classes']}"
    )


def list_image_files(directory: Path) -> List[Path]:
    """
    列出目录中的所有图片文件.
    
    Args:
        directory: 目录路径
        
    Returns:
        图片文件路径列表
    """
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
    image_files = []
    
    for file in directory.iterdir():
        if file.is_file() and file.suffix.lower() in image_extensions:
            image_files.append(file)
    
    return image_files


def get_dataset_stats(data_path: Path, class_names: List[str]) -> dict:
    """
    获取数据集统计信息.
    
    Args:
        data_path: 数据目录路径
        class_names: 类别名称列表
        
    Returns:
        统计信息字典
    """
    stats = {
        'num_classes': len(class_names),
        'total_images': 0,
        'class_distribution': {}
    }
    
    for class_name in class_names:
        class_dir = data_path / class_name
        if not class_dir.exists():
            stats['class_distribution'][class_name] = 0
            continue
        
        image_files = list_image_files(class_dir)
        count = len(image_files)
        stats['class_distribution'][class_name] = count
        stats['total_images'] += count
    
    return stats


def check_image_corrupted(image_path: Path) -> bool:
    """
    检查图片文件是否损坏.
    
    Args:
        image_path: 图片文件路径
        
    Returns:
        True if corrupted, False otherwise
    """
    try:
        with Image.open(image_path) as img:
            img.verify()  # 验证图片
        return False
    except Exception:
        return True


def validate_images_in_folder(data_path: Path, sample_ratio: float = 0.1) -> dict:
    """
    抽样验证文件夹中的图片是否损坏.
    
    Args:
        data_path: 数据目录路径
        sample_ratio: 抽样比例（0-1之间）
        
    Returns:
        验证结果字典
    """
    import random
    
    results = {
        'total_checked': 0,
        'corrupted_files': [],
        'valid_files': 0
    }
    
    # 获取所有图片文件
    all_images = []
    for class_dir in data_path.iterdir():
        if class_dir.is_dir():
            all_images.extend(list_image_files(class_dir))
    
    # 抽样
    sample_size = max(10, int(len(all_images) * sample_ratio))
    sample_images = random.sample(all_images, min(sample_size, len(all_images)))
    
    # 检查抽样图片
    for img_path in sample_images:
        results['total_checked'] += 1
        if check_image_corrupted(img_path):
            results['corrupted_files'].append(str(img_path))
        else:
            results['valid_files'] += 1
    
    if results['corrupted_files']:
        logger.warning(
            f"发现{len(results['corrupted_files'])}个损坏的图片文件 "
            f"(抽样检查{results['total_checked']}个)"
        )
    else:
        logger.info(f"抽样验证通过: 检查{results['total_checked']}个图片，未发现损坏")
    
    return results
