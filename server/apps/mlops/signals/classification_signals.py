"""
分类任务相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.classification import (
    ClassificationDatasetRelease,
    ClassificationServing,
    ClassificationTrainData,
    ClassificationTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="Classification",
    dispatch_uid_prefix="clf",
    dataset_release_model=ClassificationDatasetRelease,
    train_data_model=ClassificationTrainData,
    train_job_model=ClassificationTrainJob,
    serving_model=ClassificationServing,
    metadata_strategy=MetadataDeleteStrategy.MINIO_BACKEND,
)
