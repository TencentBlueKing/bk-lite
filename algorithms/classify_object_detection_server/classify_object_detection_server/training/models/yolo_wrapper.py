"""YOLO MLflow包装器."""

import json
from typing import Any, Dict
import mlflow
from pathlib import Path
from loguru import logger


class YOLODetectionWrapper(mlflow.pyfunc.PythonModel):
    """YOLO目标检测模型的MLflow pyfunc包装器.

    用于将YOLO检测模型保存为MLflow标准格式，支持统一的推理接口。
    """

    def load_context(self, context):
        """
        加载模型上下文.

        Args:
            context: MLflow模型上下文，包含artifacts路径
        """
        from ultralytics import YOLO

        # 加载YOLO权重
        weights_path = context.artifacts["weights"]
        self.model = YOLO(weights_path)
        logger.info(f"YOLO检测模型已加载: {weights_path}")

        # 加载类别名称
        class_names_path = context.artifacts["class_names"]
        with open(class_names_path, "r", encoding="utf-8") as f:
            self.class_names = json.load(f)
        logger.info(f"类别名称已加载: {len(self.class_names)}个类别")

    def predict(self, context, model_input):
        """
        执行目标检测预测.

        Args:
            context: MLflow上下文（未使用，但必须保留）
            model_input: 输入数据
                - 可以是图片路径列表
                - 可以是PIL Image对象列表
                - 可以是包含'images'字段的字典
                - 可以是包含'images'和推理参数的字典（如conf、iou）

        Returns:
            预测结果列表，每个元素包含:
                - boxes: 边界框列表，每个框为[x1, y1, x2, y2]（归一化坐标）
                - classes: 类别ID列表
                - confidences: 置信度列表
                - labels: 类别名称列表
        """
        # 处理输入格式
        if isinstance(model_input, dict):
            images = model_input.get("images", model_input)
            # 支持自定义推理参数
            conf = model_input.get("conf", 0.25)
            iou = model_input.get("iou", 0.45)
            imgsz = model_input.get("imgsz", 640)
        else:
            images = model_input
            conf = 0.25
            iou = 0.45
            imgsz = 640

        # 执行预测
        results = self.model.predict(
            images, conf=conf, iou=iou, imgsz=imgsz, verbose=False
        )

        # 格式化输出
        predictions = []
        for result in results:
            if result.boxes is None or len(result.boxes) == 0:
                # 未检测到任何目标
                predictions.append(
                    {
                        "boxes": [],
                        "classes": [],
                        "confidences": [],
                        "labels": [],
                        "count": 0,
                    }
                )
                continue

            # 提取检测结果
            boxes = result.boxes.xyxyn.cpu().numpy().tolist()  # 归一化坐标
            classes = result.boxes.cls.cpu().numpy().astype(int).tolist()
            confidences = result.boxes.conf.cpu().numpy().tolist()

            # 转换类别ID到类别名称
            labels = []
            for cls_id in classes:
                if cls_id < len(self.class_names):
                    labels.append(self.class_names[cls_id])
                else:
                    labels.append(f"unknown_{cls_id}")

            prediction = {
                "boxes": boxes,
                "classes": classes,
                "confidences": confidences,
                "labels": labels,
                "count": len(boxes),
            }

            predictions.append(prediction)

        return predictions
