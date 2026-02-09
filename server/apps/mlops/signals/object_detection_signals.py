"""
目标检测相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.object_detection import (
    ObjectDetectionDatasetRelease,
    ObjectDetectionServing,
    ObjectDetectionTrainData,
    ObjectDetectionTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="ObjectDetection",
    dispatch_uid_prefix="od",
    dataset_release_model=ObjectDetectionDatasetRelease,
    train_data_model=ObjectDetectionTrainData,
    train_job_model=ObjectDetectionTrainJob,
    serving_model=ObjectDetectionServing,
    metadata_strategy=MetadataDeleteStrategy.NONE,
)
