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
        
        # 加载YOLO权重
        weights_path = context.artifacts["weights"]
        self.model = YOLO(weights_path)
        logger.info(f"YOLO模型已加载: {weights_path}")
        
        # 加载类别名称
        class_names_path = context.artifacts["class_names"]
        with open(class_names_path, 'r', encoding='utf-8') as f:
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
        if isinstance(model_input, dict) and 'images' in model_input:
            images = model_input['images']
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
                'class_id': int(probs.top1),
                'class_name': self.class_names[probs.top1],
                'confidence': float(probs.top1conf),
                'top5': [
                    {
                        'class_id': int(idx),
                        'class_name': self.class_names[idx],
                        'confidence': float(conf)
                    }
                    for idx, conf in zip(top5_indices, top5_confidences)
                ]
            }
            
            predictions.append(prediction)
        
        return predictions
