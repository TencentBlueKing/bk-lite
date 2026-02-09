"""
异常检测相关的 Celery 任务
"""

from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from apps.core.logger import mlops_logger as logger
from apps.mlops.tasks.base import (
    DatasetPublishConfig,
    build_base_metadata,
    count_csv_samples,
    mark_release_as_failed,
    publish_dataset_release_base,
)


def _get_anomaly_count(data_obj: Any) -> int:
    """从训练数据对象的 metadata 中提取异常点数量"""
    if not data_obj.metadata:
        return 0
    # S3JSONField 会自动加载为 dict
    metadata = data_obj.metadata if isinstance(data_obj.metadata, dict) else {}
    anomaly_point = metadata.get("anomaly_point", [])
    return len(anomaly_point) if isinstance(anomaly_point, list) else 0


def _build_anomaly_detection_metadata(
    train_samples: int,
    val_samples: int,
    test_samples: int,
    train_obj: Any,
    val_obj: Any,
    test_obj: Any,
    train_file_id: int,
    val_file_id: int,
    test_file_id: int,
) -> dict[str, Any]:
    """构建异常检测数据集元信息，包含异常点统计"""
    # 从各数据对象的 metadata 中提取异常点数量
    train_anomaly_count = _get_anomaly_count(train_obj)
    val_anomaly_count = _get_anomaly_count(val_obj)
    test_anomaly_count = _get_anomaly_count(test_obj)
    total_anomaly_count = train_anomaly_count + val_anomaly_count + test_anomaly_count
    total_samples = train_samples + val_samples + test_samples

    return build_base_metadata(
        train_samples,
        val_samples,
        test_samples,
        train_obj,
        val_obj,
        test_obj,
        train_file_id,
        val_file_id,
        test_file_id,
        extra_fields={
            "train_anomaly_count": train_anomaly_count,
            "val_anomaly_count": val_anomaly_count,
            "test_anomaly_count": test_anomaly_count,
            "total_anomaly_count": total_anomaly_count,
            "anomaly_rate": round(total_anomaly_count / total_samples, 4)
            if total_samples > 0
            else 0,
            "features": ["timestamp", "value"],
            "data_types": {"timestamp": "string", "value": "float"},
        },
    )


def _get_config() -> DatasetPublishConfig:
    """延迟加载配置，避免循环导入"""
    from apps.mlops.models.anomaly_detection import (
        AnomalyDetectionDatasetRelease,
        AnomalyDetectionTrainData,
    )

    return DatasetPublishConfig(
        release_model=AnomalyDetectionDatasetRelease,
        train_data_model=AnomalyDetectionTrainData,
        task_type="anomaly_detection",
        file_extension="csv",
        storage_prefix="anomaly_detection_datasets",
        count_samples=count_csv_samples,
        build_metadata=_build_anomaly_detection_metadata,
    )


@shared_task(
    soft_time_limit=3600,  # 60 分钟
    time_limit=3660,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_dataset_release_async(
    release_id: int, train_file_id: int, val_file_id: int, test_file_id: int
) -> dict[str, Any]:
    """
    异步发布异常检测数据集版本

    Args:
        release_id: AnomalyDetectionDatasetRelease 的主键
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果
    """
    try:
        config = _get_config()
        return publish_dataset_release_base(
            config, release_id, train_file_id, val_file_id, test_file_id
        )

    except SoftTimeLimitExceeded:
        logger.error(f"数据集发布超时 - Release ID: {release_id}")
        from apps.mlops.models.anomaly_detection import AnomalyDetectionDatasetRelease

        mark_release_as_failed(AnomalyDetectionDatasetRelease, release_id)
        raise

    except Exception:
        logger.error(f"数据集发布失败 - Release ID: {release_id}", exc_info=True)
        from apps.mlops.models.anomaly_detection import AnomalyDetectionDatasetRelease

        mark_release_as_failed(AnomalyDetectionDatasetRelease, release_id)
        raise
