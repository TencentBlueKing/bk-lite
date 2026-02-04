"""图像预处理器."""

from pathlib import Path
from typing import Optional
from loguru import logger
from PIL import Image


class ImagePreprocessor:
    """图像预处理器.

    负责图像验证、格式检查等预处理任务。
    实际的transforms由YOLO内部处理。
    """

    def __init__(self, config: dict = None):
        """
        初始化预处理器.

        Args:
            config: 预处理配置字典
        """
        self.config = config or {}
        self.supported_formats = self.config.get(
            "allowed_extensions",
            [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".webp"],
        )
        self.min_image_size = self.config.get("min_image_size", 32)
        self.check_corrupted = self.config.get("check_corrupted", False)

        logger.info(f"ImagePreprocessor初始化: 支持格式={self.supported_formats}")

    def validate_dataset(self, dataset_yaml_path: str) -> dict:
        """
        验证目标检测数据集.

        Args:
            dataset_yaml_path: YOLO格式数据集配置文件路径（data.yaml 或 dataset.yaml）

        Returns:
            验证结果字典
        """
        from ..data_loader import validate_yolo_dataset

        logger.info(f"验证目标检测数据集: {dataset_yaml_path}")

        results = {"valid": True, "errors": []}

        # 检查YAML文件是否存在
        yaml_path = Path(dataset_yaml_path)
        if not yaml_path.exists():
            results["valid"] = False
            results["errors"].append(f"数据集配置文件不存在: {dataset_yaml_path}")
            return results

        # 验证YOLO数据集结构
        try:
            validate_yolo_dataset(dataset_yaml_path)
            logger.info("数据集验证通过")
        except Exception as e:
            results["valid"] = False
            results["errors"].append(str(e))
            logger.warning(f"数据集验证失败: {e}")

        return results

    def check_image_format(self, image_path: Path) -> bool:
        """
        检查图像格式是否支持.

        Args:
            image_path: 图像文件路径

        Returns:
            True if supported
        """
        return image_path.suffix.lower() in self.supported_formats

    def check_image_size(self, image_path: Path) -> bool:
        """
        检查图像尺寸是否满足最小要求.

        Args:
            image_path: 图像文件路径

        Returns:
            True if size is adequate
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size
                return width >= self.min_image_size and height >= self.min_image_size
        except Exception:
            return False
