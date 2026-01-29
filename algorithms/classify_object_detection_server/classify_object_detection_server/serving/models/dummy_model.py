"""Dummy model for demonstration and testing."""

from typing import List, Dict, Any
from loguru import logger


class DummyModel:
    """模拟目标检测模型，返回固定的检测结果."""

    def __init__(self):
        """初始化模拟模型."""
        self.version = "0.1.0-dummy"
        self.class_names = ["cat", "dog", "person", "car", "bicycle"]
        logger.info("DummyModel initialized for object detection")

    def predict(self, model_input: Any) -> List[Dict[str, Any]]:
        """
        模拟目标检测预测.

        Args:
            model_input: 输入数据（可以是图片列表或字典）

        Returns:
            预测结果列表，每个元素包含:
                - boxes: 边界框列表 [[x1, y1, x2, y2], ...]（归一化坐标）
                - classes: 类别ID列表
                - confidences: 置信度列表
                - labels: 类别名称列表
                - count: 检测目标数量

        Note:
            返回格式与 YOLOWrapper.predict() 保持一致
        """
        # 处理输入
        if isinstance(model_input, dict):
            images = model_input.get("images", [])
            batch_size = len(images) if isinstance(images, list) else 1
        elif isinstance(model_input, list):
            batch_size = len(model_input)
        else:
            batch_size = 1

        logger.debug(f"DummyModel predict for batch_size={batch_size}")

        # 为每张图片生成模拟检测结果
        predictions = []
        for i in range(batch_size):
            # 生成2-3个模拟检测框
            num_detections = 2 + (i % 2)  # 2或3个检测框

            prediction = {
                "boxes": [
                    [0.1 + i * 0.01, 0.2, 0.5, 0.6],  # [x1, y1, x2, y2] 归一化坐标
                    [0.6, 0.3 + i * 0.01, 0.9, 0.8],
                ][:num_detections],
                "classes": [0, 2][:num_detections],  # cat, person
                "confidences": [0.85, 0.72][:num_detections],
                "labels": ["cat", "person"][:num_detections],
                "count": num_detections,
            }

            if num_detections == 3:
                prediction["boxes"].append([0.15, 0.65, 0.45, 0.95])
                prediction["classes"].append(3)  # car
                prediction["confidences"].append(0.68)
                prediction["labels"].append("car")

            predictions.append(prediction)

        logger.debug(f"DummyModel generated {len(predictions)} predictions")
        return predictions
