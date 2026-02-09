"""
异常检测相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionServing,
    AnomalyDetectionTrainData,
    AnomalyDetectionTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="AnomalyDetection",
    dispatch_uid_prefix="ad",
    dataset_release_model=AnomalyDetectionDatasetRelease,
    train_data_model=AnomalyDetectionTrainData,
    train_job_model=AnomalyDetectionTrainJob,
    serving_model=AnomalyDetectionServing,
    metadata_strategy=MetadataDeleteStrategy.HASATTR,
)
