"""
时间序列预测相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_minio_backend import MinioBackend

from apps.core.logger import mlops_logger as logger
from apps.mlops.models.timeseries_predict import (
    TimeSeriesPredictDatasetRelease,
    TimeSeriesPredictTrainData,
    TimeSeriesPredictTrainJob,
)


@receiver(
    post_delete,
    sender=TimeSeriesPredictDatasetRelease,
    dispatch_uid="cleanup_ts_dataset_release",
)
def cleanup_dataset_release_files(sender, instance, **kwargs):
    """
    清理数据集发布版本的 MinIO 文件

    在 TimeSeriesPredictDatasetRelease 删除后触发,删除 MinIO 中的压缩包文件
    """
    logger.info(
        f"[Signal] post_delete 触发: TimeSeriesPredictDatasetRelease, "
        f"release_id={instance.id}, version={instance.version}, "
        f"has_dataset_file={bool(instance.dataset_file)}"
    )

    def delete_files():
        try:
            if instance.dataset_file:
                instance.dataset_file.delete(save=False)
                logger.info(
                    f"成功删除数据集发布文件: {instance.dataset_file.name}, "
                    f"release_id={instance.id}, version={instance.version}"
                )
            else:
                logger.warning(
                    f"数据集发布版本没有关联文件, "
                    f"release_id={instance.id}, version={instance.version}"
                )
        except Exception as e:
            logger.error(
                f"删除数据集发布文件失败: {str(e)}, "
                f"release_id={instance.id}, version={instance.version}"
            )

    transaction.on_commit(delete_files)


@receiver(
    post_delete, sender=TimeSeriesPredictTrainData, dispatch_uid="cleanup_ts_train_data"
)
def cleanup_train_data_files(sender, instance, **kwargs):
    """
    清理训练数据的 MinIO 文件

    在 TimeSeriesPredictTrainData 删除后触发,删除训练数据文件和元数据文件
    """
    logger.info(
        f"[Signal] post_delete 触发: TimeSeriesPredictTrainData, "
        f"train_data_id={instance.id}, name={instance.name}, "
        f"has_train_data={bool(instance.train_data)}, "
        f"has_metadata={bool(instance.metadata)}"
    )

    def delete_files():
        try:
            # 删除 FileField (train_data)
            if instance.train_data:
                instance.train_data.delete(save=False)
                logger.info(
                    f"成功删除训练数据文件: {instance.train_data.name}, "
                    f"train_data_id={instance.id}, name={instance.name}"
                )

            # 删除 S3JSONField (metadata) - 需要通过 storage 手动删除
            if instance.metadata:
                storage = MinioBackend(bucket_name="munchkin-public")
                storage.delete(instance.metadata)
                logger.info(
                    f"成功删除元数据文件: {instance.metadata}, "
                    f"train_data_id={instance.id}, name={instance.name}"
                )

        except Exception as e:
            logger.error(
                f"删除训练数据文件失败: {str(e)}, "
                f"train_data_id={instance.id}, name={instance.name}"
            )

    transaction.on_commit(delete_files)


@receiver(
    post_delete, sender=TimeSeriesPredictTrainJob, dispatch_uid="cleanup_ts_train_job"
)
def cleanup_train_job_files(sender, instance, **kwargs):
    """
    清理训练任务的 MinIO 配置文件

    在 TimeSeriesPredictTrainJob 删除后触发,删除 config_url 文件
    """
    logger.info(
        f"[Signal] post_delete 触发: TimeSeriesPredictTrainJob, "
        f"train_job_id={instance.id}, name={instance.name}, "
        f"has_config_url={bool(instance.config_url)}"
    )

    def delete_files():
        try:
            if instance.config_url:
                instance.config_url.delete(save=False)
                logger.info(
                    f"成功删除训练任务配置文件: {instance.config_url.name}, "
                    f"train_job_id={instance.id}, name={instance.name}"
                )
            else:
                logger.debug(
                    f"训练任务没有配置文件, "
                    f"train_job_id={instance.id}, name={instance.name}"
                )
        except Exception as e:
            logger.error(
                f"删除训练任务配置文件失败: {str(e)}, "
                f"train_job_id={instance.id}, name={instance.name}"
            )

    transaction.on_commit(delete_files)
