"""图像特征工程和数据增强配置."""

from loguru import logger


class ImageFeatureEngineer:
    """图像特征工程器.
    
    注意：YOLO内置了强大的数据增强功能，包括：
    - 随机旋转、翻转、缩放
    - 颜色抖动（HSV增强）
    - Mosaic、Mixup等高级增强
    
    此类主要用于：
    1. 配置YOLO的数据增强策略
    2. 扩展自定义数据增强（如果需要）
    """
    
    def __init__(self, config: dict = None):
        """
        初始化特征工程器.
        
        Args:
            config: 特征工程配置字典
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        
        if self.enabled:
            logger.info("图像特征工程已启用（使用YOLO内置增强）")
        else:
            logger.info("图像特征工程已禁用")
    
    def get_augmentation_config(self) -> dict:
        """
        获取数据增强配置.
        
        Returns:
            增强配置字典（传递给YOLO）
        """
        if not self.enabled:
            return {'augment': False}
        
        # YOLO的数据增强由其内部处理，这里返回启用标志
        return {
            'augment': True,
            # 可以添加更多YOLO支持的增强参数
            # 'degrees': 0.0,  # 旋转角度
            # 'translate': 0.1,  # 平移
            # 'scale': 0.5,  # 缩放
            # 'fliplr': 0.5,  # 水平翻转概率
            # 'flipud': 0.0,  # 垂直翻转概率
            # 'hsv_h': 0.015,  # HSV-Hue增强
            # 'hsv_s': 0.7,  # HSV-Saturation增强
            # 'hsv_v': 0.4,  # HSV-Value增强
        }
    
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
