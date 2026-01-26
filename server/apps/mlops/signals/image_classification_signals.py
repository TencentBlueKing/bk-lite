"""
图片分类相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.logger import opspilot_logger as logger
from apps.mlops.models.image_classification import (
    ImageClassificationDatasetRelease,
    ImageClassificationTrainData,
    ImageClassificationTrainJob,
)


@receiver(
    post_delete,
    sender=ImageClassificationDatasetRelease,
    dispatch_uid="cleanup_ic_dataset_release",
)
def cleanup_dataset_release_files(sender, instance, **kwargs):
    """
    清理数据集发布版本的 MinIO 文件

    在 ImageClassificationDatasetRelease 删除后触发,删除 MinIO 中的压缩包文件
    """
    logger.info(
        f"[Signal] post_delete 触发: ImageClassificationDatasetRelease, "
        f"dataset_release_id={instance.id}, dataset_name={instance.dataset.name}, "
        f"version={instance.version}, has_dataset_file={bool(instance.dataset_file)}"
    )

    def delete_files():
        try:
            if instance.dataset_file:
                instance.dataset_file.delete(save=False)
                logger.info(
                    f"成功删除数据集发布文件: {instance.dataset_file.name}, "
                    f"dataset_release_id={instance.id}, version={instance.version}"
                )
            else:
                logger.debug(
                    f"数据集发布版本没有文件, "
                    f"dataset_release_id={instance.id}, version={instance.version}"
                )
        except Exception as e:
            logger.error(
                f"删除数据集发布文件失败: {str(e)}, "
                f"dataset_release_id={instance.id}, version={instance.version}"
            )

    transaction.on_commit(delete_files)


@receiver(
    post_delete,
    sender=ImageClassificationTrainData,
    dispatch_uid="cleanup_ic_train_data",
)
def cleanup_train_data_files(sender, instance, **kwargs):
    """
    清理训练数据的 MinIO 文件

    在 ImageClassificationTrainData 删除后触发,删除 train_data ZIP 文件
    """
    logger.info(
        f"[Signal] post_delete 触发: ImageClassificationTrainData, "
        f"train_data_id={instance.id}, name={instance.name}, "
        f"has_train_data={bool(instance.train_data)}"
    )

    def delete_files():
        try:
            # 删除训练数据文件(ZIP)
            if instance.train_data:
                instance.train_data.delete(save=False)
                logger.info(
                    f"成功删除训练数据文件: {instance.train_data.name}, "
                    f"train_data_id={instance.id}, name={instance.name}"
                )
            else:
                logger.debug(
                    f"训练数据没有关联文件, "
                    f"train_data_id={instance.id}, name={instance.name}"
                )
        except Exception as e:
            logger.error(
                f"删除训练数据文件失败: {str(e)}, "
                f"train_data_id={instance.id}, name={instance.name}"
            )

    transaction.on_commit(delete_files)


@receiver(
    post_delete, sender=ImageClassificationTrainJob, dispatch_uid="cleanup_ic_train_job"
)
def cleanup_train_job_config_file(sender, instance, **kwargs):
    """
    清理训练任务的 MinIO 配置文件

    在 ImageClassificationTrainJob 删除后触发,删除 config_url 文件
    """
    logger.info(
        f"[Signal] post_delete 触发: ImageClassificationTrainJob, "
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
