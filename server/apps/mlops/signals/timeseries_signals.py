"""
时间序列预测相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDatasetRelease,
    TimeSeriesPredictServing,
    TimeSeriesPredictTrainData,
    TimeSeriesPredictTrainJob,
)
from apps.mlops.signals.base import MetadataDeleteStrategy, register_cleanup_signals

register_cleanup_signals(
    prefix="TimeseriesPredict",
    dispatch_uid_prefix="ts",
    dataset_release_model=TimeSeriesPredictDatasetRelease,
    train_data_model=TimeSeriesPredictTrainData,
    train_job_model=TimeSeriesPredictTrainJob,
    serving_model=TimeSeriesPredictServing,
    metadata_strategy=MetadataDeleteStrategy.MINIO_BACKEND,
)
