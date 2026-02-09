"""
分类任务相关的 Celery 任务
"""

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


def _build_classification_metadata(
    train_samples,
    val_samples,
    test_samples,
    train_obj,
    val_obj,
    test_obj,
    train_file_id,
    val_file_id,
    test_file_id,
):
    """构建分类数据集元信息"""
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
    )


def _get_config():
    """延迟加载配置，避免循环导入"""
    from apps.mlops.models.classification import (
        ClassificationDatasetRelease,
        ClassificationTrainData,
    )

    return DatasetPublishConfig(
        release_model=ClassificationDatasetRelease,
        train_data_model=ClassificationTrainData,
        task_type="classification",
        file_extension="csv",
        storage_prefix="classification_datasets",
        count_samples=count_csv_samples,
        build_metadata=_build_classification_metadata,
    )


@shared_task(
    soft_time_limit=3600,  # 60 分钟
    time_limit=3660,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_dataset_release_async(release_id, train_file_id, val_file_id, test_file_id):
    """
    异步发布数据集版本

    Args:
        release_id: ClassificationDatasetRelease 的主键
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
        from apps.mlops.models.classification import ClassificationDatasetRelease

        mark_release_as_failed(ClassificationDatasetRelease, release_id)
        raise

    except Exception:
        logger.error(f"数据集发布失败 - Release ID: {release_id}", exc_info=True)
        from apps.mlops.models.classification import ClassificationDatasetRelease

        mark_release_as_failed(ClassificationDatasetRelease, release_id)
        raise
