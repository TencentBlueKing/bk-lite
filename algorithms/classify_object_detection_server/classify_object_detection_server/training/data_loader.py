"""YOLO数据集加载器."""

from typing import Optional
from pathlib import Path
import yaml
from loguru import logger


class DataLoaderError(Exception):
    """数据加载错误异常."""

    pass


def load_yolo_dataset(dataset_yaml_path: str) -> str:
    """
    加载YOLO格式数据集.

    Args:
        dataset_yaml_path: data.yaml文件路径（支持 data.yaml 或 dataset.yaml）

    Returns:
        data.yaml的绝对路径（YOLO训练时使用）

    Raises:
        DataLoaderError: 数据集格式错误或文件不存在

    Note:
        期望的data.yaml格式:
        ```yaml
        path: /absolute/path/to/dataset  # 数据集根目录
        train: images/train              # 训练集图片目录（相对路径）
        val: images/val                  # 验证集图片目录
        test: images/test                # 测试集图片目录（可选）

        nc: 80                           # 类别数
        names:                           # 类别名称列表
          0: person
          1: bicycle
          ...
        ```
    """
    yaml_path = Path(dataset_yaml_path)

    # 检查文件存在性
    if not yaml_path.exists():
        raise DataLoaderError(f"数据集配置文件不存在: {dataset_yaml_path}")

    # 加载YAML配置
    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            dataset_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise DataLoaderError(f"YAML文件格式错误: {e}")
    except Exception as e:
        raise DataLoaderError(f"读取YAML文件失败: {e}")

    # 验证必需字段（nc 可选，可从 names 推断）
    required_fields = ["path", "train", "val", "names"]
    missing_fields = [field for field in required_fields if field not in dataset_config]
    if missing_fields:
        raise DataLoaderError(f"数据集配置缺少必需字段: {missing_fields}")

    # 获取类别信息
    names = dataset_config["names"]
    if not isinstance(names, (list, dict)):
        raise DataLoaderError(f"类别名称格式错误，应为列表或字典，实际: {type(names)}")

    # 统一转换为列表格式并推断类别数
    if isinstance(names, dict):
        # 从字典推断类别数
        nc = len(names)
        names_list = [names.get(i, f"class_{i}") for i in range(nc)]
    else:
        # 从列表推断类别数
        nc = len(names)
        names_list = names

    # 如果配置中指定了 nc，验证一致性
    if "nc" in dataset_config:
        config_nc = dataset_config["nc"]
        if not isinstance(config_nc, int) or config_nc <= 0:
            raise DataLoaderError(f"无效的类别数量: {config_nc}，必须是正整数")
        if config_nc != nc:
            raise DataLoaderError(f"配置中的 nc({config_nc}) 与 names 数量({nc})不匹配")
        logger.info(f"✓ 配置中的 nc 字段与 names 一致: {nc}")
    else:
        logger.info(f"✓ 从 names 推断类别数: {nc}")

    # 验证路径存在性
    dataset_root = Path(dataset_config["path"])
    if not dataset_root.is_absolute():
        # 如果是相对路径，基于yaml文件位置解析
        dataset_root = (yaml_path.parent / dataset_root).resolve()

    # 修正data.yaml中的path字段为绝对路径，避免YOLO内部路径解析错误
    if dataset_config["path"] != str(dataset_root):
        logger.info(
            f"修正data.yaml中的相对路径: {dataset_config['path']} -> {dataset_root}"
        )
        dataset_config["path"] = str(dataset_root)
        try:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(dataset_config, f, sort_keys=False, allow_unicode=True)
            logger.info(f"✓ 已更新data.yaml为绝对路径")
        except Exception as e:
            logger.warning(f"⚠️  无法更新data.yaml: {e}，YOLO可能会遇到路径问题")

    if not dataset_root.exists():
        logger.warning(
            f"⚠️  数据集根目录不存在: {dataset_root}\n"
            f"   如果数据集尚未下载，请先准备数据"
        )

    # 验证train/val路径配置
    train_path = dataset_root / dataset_config["train"]
    val_path = dataset_root / dataset_config["val"]

    # 检查测试集（可选）
    test_config = dataset_config.get("test")
    test_path = dataset_root / test_config if test_config else None

    # 日志输出
    logger.info("=" * 60)
    logger.info("YOLO数据集配置加载成功")
    logger.info(f"数据集根目录: {dataset_root}")
    logger.info(f"训练集: {train_path} ({'存在' if train_path.exists() else '不存在'})")
    logger.info(f"验证集: {val_path} ({'存在' if val_path.exists() else '不存在'})")
    if test_path:
        logger.info(
            f"测试集: {test_path} ({'存在' if test_path.exists() else '不存在'})"
        )
    logger.info(f"类别数量: {nc}")
    logger.info(f"类别名称: {names_list[:5]}{'...' if nc > 5 else ''}")
    logger.info("=" * 60)

    # 返回绝对路径（YOLO要求）
    return str(yaml_path.resolve())


def validate_yolo_dataset(dataset_yaml_path: str) -> dict:
    """
    验证YOLO数据集的完整性.

    Args:
        dataset_yaml_path: data.yaml文件路径（支持 data.yaml 或 dataset.yaml）

    Returns:
        验证结果字典:
        {
            'valid': bool,
            'errors': List[str],
            'warnings': List[str],
            'stats': {
                'train_images': int,
                'val_images': int,
                'test_images': int,
                'nc': int
            }
        }
    """
    errors = []
    warnings = []
    stats = {"train_images": 0, "val_images": 0, "test_images": 0, "nc": 0}

    try:
        yaml_path = Path(dataset_yaml_path)

        # 加载配置
        with open(yaml_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        dataset_root = Path(config["path"])
        if not dataset_root.is_absolute():
            dataset_root = (yaml_path.parent / dataset_root).resolve()

        # 检查train目录
        train_path = dataset_root / config["train"]
        if not train_path.exists():
            errors.append(f"训练集目录不存在: {train_path}")
        else:
            train_images = list(train_path.glob("*.jpg")) + list(
                train_path.glob("*.png")
            )
            stats["train_images"] = len(train_images)
            if stats["train_images"] == 0:
                warnings.append(f"训练集目录为空: {train_path}")

        # 检查val目录
        val_path = dataset_root / config["val"]
        if not val_path.exists():
            errors.append(f"验证集目录不存在: {val_path}")
        else:
            val_images = list(val_path.glob("*.jpg")) + list(val_path.glob("*.png"))
            stats["val_images"] = len(val_images)
            if stats["val_images"] == 0:
                warnings.append(f"验证集目录为空: {val_path}")

        # 检查test目录（可选）
        if "test" in config:
            test_path = dataset_root / config["test"]
            if test_path.exists():
                test_images = list(test_path.glob("*.jpg")) + list(
                    test_path.glob("*.png")
                )
                stats["test_images"] = len(test_images)

        stats["nc"] = config.get("nc", 0)

    except Exception as e:
        errors.append(f"验证失败: {str(e)}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }
