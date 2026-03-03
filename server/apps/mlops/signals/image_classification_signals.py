"""
图片分类相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.image_classification import (
    ImageClassificationDatasetRelease,
    ImageClassificationServing,
    ImageClassificationTrainData,
    ImageClassificationTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="ImageClassification",
    dispatch_uid_prefix="ic",
    dataset_release_model=ImageClassificationDatasetRelease,
    train_data_model=ImageClassificationTrainData,
    train_job_model=ImageClassificationTrainJob,
    serving_model=ImageClassificationServing,
    metadata_strategy=MetadataDeleteStrategy.NONE,
)
