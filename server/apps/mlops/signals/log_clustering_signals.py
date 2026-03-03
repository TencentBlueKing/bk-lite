"""
日志聚类相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.log_clustering import (
    LogClusteringDatasetRelease,
    LogClusteringServing,
    LogClusteringTrainData,
    LogClusteringTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="LogClustering",
    dispatch_uid_prefix="lc",
    dataset_release_model=LogClusteringDatasetRelease,
    train_data_model=LogClusteringTrainData,
    train_job_model=LogClusteringTrainJob,
    serving_model=LogClusteringServing,
    metadata_strategy=MetadataDeleteStrategy.MINIO_BACKEND,
)
