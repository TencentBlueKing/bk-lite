"""图像预处理器."""

from pathlib import Path
from typing import List, Optional
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
            'image_formats', 
            ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
        )
        self.min_image_size = self.config.get('min_image_size', 32)
        self.check_corrupted = self.config.get('check_corrupted', False)
        
        logger.info(f"ImagePreprocessor初始化: 支持格式={self.supported_formats}")
    
    def validate_dataset(self, dataset_path: str) -> dict:
        """
        验证数据集.
        
        Args:
            dataset_path: 数据集路径
            
        Returns:
            验证结果字典
        """
        from ..data_loader import validate_images_in_folder
        
        dataset_path = Path(dataset_path)
        logger.info(f"验证数据集: {dataset_path}")
        
        results = {
            'valid': True,
            'errors': []
        }
        
        # 检查目录是否存在
        if not dataset_path.exists():
            results['valid'] = False
            results['errors'].append(f"数据集目录不存在: {dataset_path}")
            return results
        
        # 可选：检查图像是否损坏
        if self.check_corrupted:
            logger.info("检查图像完整性...")
            check_results = validate_images_in_folder(dataset_path, sample_ratio=0.1)
            if check_results['corrupted_files']:
                results['valid'] = False
                results['errors'].extend(check_results['corrupted_files'])
        
        if results['valid']:
            logger.info("数据集验证通过")
        else:
            logger.warning(f"数据集验证失败: {len(results['errors'])}个错误")
        
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
