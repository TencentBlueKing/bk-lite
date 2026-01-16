"""配置Schema定义."""

from typing import List

# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "YOLOv11Detection",  # YOLOv11目标检测模型
]

# 支持的设备类型
SUPPORTED_DEVICES: List[str] = [
    "auto",  # 自动检测（优先GPU）
    "cpu",  # 强制CPU
    "gpu",  # 单GPU
    "gpus",  # 多GPU分布式训练
]

# 支持的评估指标
SUPPORTED_METRICS: List[str] = [
    "mAP50",  # mAP@0.5
    "mAP50-95",  # mAP@0.5:0.95
    "precision",  # 精确率
    "recall",  # 召回率
]
