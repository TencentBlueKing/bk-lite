"""YOLO MLflow包装器."""

import json
from typing import Any, Dict
import mlflow
from pathlib import Path
from loguru import logger


class YOLOClassificationWrapper(mlflow.pyfunc.PythonModel):
    """YOLO分类模型的MLflow pyfunc包装器.

    用于将YOLO模型保存为MLflow标准格式，支持统一的推理接口。
    """

    def load_context(self, context):
        """
        加载模型上下文.

        Args:
            context: MLflow模型上下文，包含artifacts路径
        """
        from ultralytics import YOLO
        from pathlib import Path
        import os

        # 加载YOLO权重 - 标准化路径以确保跨平台兼容性
        weights_path_raw = context.artifacts["weights"]
        # 将 Windows 风格的反斜杠替换为正斜杠，然后使用 Path 标准化
        weights_path = Path(str(weights_path_raw).replace("\\", "/"))

        # 如果路径不存在，尝试在当前工作目录或相对路径中查找
        if not weights_path.exists():
            # 尝试仅使用文件名
            weights_filename = Path(weights_path_raw).name
            # 在 artifacts 目录中查找
            for artifact_key, artifact_path in context.artifacts.items():
                artifact_dir = Path(artifact_path).parent
                candidate_path = artifact_dir / weights_filename
                if candidate_path.exists():
                    weights_path = candidate_path
                    break

        if not weights_path.exists():
            raise FileNotFoundError(
                f"YOLO权重文件不存在: {weights_path}\n"
                f"原始路径: {weights_path_raw}\n"
                f"当前工作目录: {os.getcwd()}\n"
                f"Artifacts: {context.artifacts}"
            )

        self.model = YOLO(str(weights_path))
        logger.info(f"YOLO模型已加载: {weights_path}")

        # 加载类别名称 - 同样标准化路径
        class_names_path_raw = context.artifacts["class_names"]
        class_names_path = Path(str(class_names_path_raw).replace("\\", "/"))

        # 如果路径不存在，尝试查找
        if not class_names_path.exists():
            class_names_filename = Path(class_names_path_raw).name
            for artifact_key, artifact_path in context.artifacts.items():
                artifact_dir = Path(artifact_path).parent
                candidate_path = artifact_dir / class_names_filename
                if candidate_path.exists():
                    class_names_path = candidate_path
                    break

        if not class_names_path.exists():
            raise FileNotFoundError(
                f"类别名称文件不存在: {class_names_path}\n"
                f"原始路径: {class_names_path_raw}"
            )

        with open(class_names_path, "r", encoding="utf-8") as f:
            self.class_names = json.load(f)
        logger.info(f"类别名称已加载: {len(self.class_names)}个类别")

    def predict(self, context, model_input):
        """
        执行预测.

        Args:
            context: MLflow上下文（未使用，但必须保留）
            model_input: 输入数据
                - 可以是图片路径列表
                - 可以是PIL Image对象列表
                - 可以是包含'images'字段的字典

        Returns:
            预测结果列表，每个元素包含:
                - class_id: 类别索引
                - class_name: 类别名称
                - confidence: 置信度
                - top5: Top-5预测结果
        """
        # 处理输入格式
        if isinstance(model_input, dict) and "images" in model_input:
            images = model_input["images"]
        else:
            images = model_input

        # 执行预测
        results = self.model.predict(images, verbose=False)

        # 格式化输出
        predictions = []
        for result in results:
            probs = result.probs

            # 获取top5预测
            top5_indices = probs.top5
            top5_confidences = probs.top5conf

            prediction = {
                "class_id": int(probs.top1),
                "class_name": self.class_names[probs.top1],
                "confidence": float(probs.top1conf),
                "top5": [
                    {
                        "class_id": int(idx),
                        "class_name": self.class_names[idx],
                        "confidence": float(conf),
                    }
                    for idx, conf in zip(top5_indices, top5_confidences)
                ],
            }

            predictions.append(prediction)

        return predictions
