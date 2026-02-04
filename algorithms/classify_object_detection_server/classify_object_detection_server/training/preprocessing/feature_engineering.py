"""图像特征工程和数据增强配置."""

from loguru import logger


class ImageFeatureEngineer:
    """目标检测特征工程器.

    注意：YOLO内置了强大的数据增强功能，专门为目标检测优化：
    - 随机旋转、翻转、缩放、平移
    - 颜色抖动（HSV增强）
    - Mosaic增强（多图拼接）
    - Mixup增强（图像混合）
    - Copy-Paste增强

    此类主要用于：
    1. 配置YOLO的数据增强策略
    2. 传递检测专用的增强参数
    """

    def __init__(self, config: dict = None):
        """
        初始化特征工程器.

        Args:
            config: 特征工程配置字典
        """
        self.config = config or {}
        self.enabled = self.config.get("augmentation_enabled", True)

        if self.enabled:
            logger.info("图像特征工程已启用（使用YOLO内置增强）")
        else:
            logger.info("图像特征工程已禁用")

    def get_augmentation_config(self) -> dict:
        """
        获取目标检测数据增强配置.

        Returns:
            增强配置字典（传递给YOLO训练）
        """
        if not self.enabled:
            return {"augment": False}

        # YOLO会使用默认的数据增强策略
        # 用户如果需要微调增强参数，可以在 hyperparams 中传递
        return {"augment": True}

    def transform(self, image):
        """
        应用自定义转换（预留接口）.

        Args:
            image: PIL Image对象

        Returns:
            转换后的图像
        """
        # YOLO会自动处理transforms，这里暂时直接返回
        return image
