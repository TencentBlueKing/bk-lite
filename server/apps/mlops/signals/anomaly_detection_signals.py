"""
异常检测相关的 Django Signal 处理器

处理模型删除时的 MinIO 文件清理
"""

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.core.logger import mlops_logger as logger
from apps.mlops.models.anomaly_detection import (
    AnomalyDetectionDatasetRelease,
    AnomalyDetectionTrainData,
    AnomalyDetectionTrainJob,
    AnomalyDetectionServing,
)


@receiver(
    post_delete,
    sender=AnomalyDetectionDatasetRelease,
    dispatch_uid="cleanup_ad_dataset_release",
)
def cleanup_dataset_release_files(sender, instance, **kwargs):
    """
    清理数据集发布版本的 MinIO 文件

    在 AnomalyDetectionDatasetRelease 删除后触发,删除 MinIO 中的压缩包文件
    """
    logger.info(
        f"[Signal] post_delete 触发: AnomalyDetectionDatasetRelease, "
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
    post_delete, sender=AnomalyDetectionTrainData, dispatch_uid="cleanup_ad_train_data"
)
def cleanup_train_data_files(sender, instance, **kwargs):
    """
    清理训练数据的 MinIO 文件

    在 AnomalyDetectionTrainData 删除后触发,删除 train_data 和 metadata 文件
    """
    logger.info(
        f"[Signal] post_delete 触发: AnomalyDetectionTrainData, "
        f"train_data_id={instance.id}, name={instance.name}, "
        f"has_train_data={bool(instance.train_data)}, "
        f"has_metadata={bool(instance.metadata)}"
    )

    def delete_files():
        try:
            # 删除训练数据文件
            if instance.train_data:
                instance.train_data.delete(save=False)
                logger.info(
                    f"成功删除训练数据文件: {instance.train_data.name}, "
                    f"train_data_id={instance.id}, name={instance.name}"
                )

            # 删除元数据文件(S3JSONField)
            if instance.metadata:
                # S3JSONField 的删除需要特殊处理
                try:
                    # 尝试删除底层文件
                    if hasattr(instance.metadata, "delete"):
                        instance.metadata.delete(save=False)
                        logger.info(
                            f"成功删除元数据文件, "
                            f"train_data_id={instance.id}, name={instance.name}"
                        )
                except Exception as metadata_error:
                    logger.warning(
                        f"删除元数据文件时出现警告: {str(metadata_error)}, "
                        f"train_data_id={instance.id}"
                    )

            if not instance.train_data and not instance.metadata:
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
    post_delete, sender=AnomalyDetectionTrainJob, dispatch_uid="cleanup_ad_train_job"
)
def cleanup_train_job_config_file(sender, instance, **kwargs):
    """
    清理训练任务的 MinIO 配置文件

    在 AnomalyDetectionTrainJob 删除后触发,删除 config_url 文件
    """
    logger.info(
        f"[Signal] post_delete 触发: AnomalyDetectionTrainJob, "
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


# ==================== MLflow 和 Docker 资源清理 ====================

from apps.mlops.utils import mlflow_service
from apps.mlops.utils.webhook_client import WebhookClient, WebhookError


@receiver(
    post_delete,
    sender=AnomalyDetectionTrainJob,
    dispatch_uid="cleanup_ad_mlflow_experiment",
)
def cleanup_mlflow_experiment(sender, instance, **kwargs):
    """
    清理 MLflow 实验和模型

    在 AnomalyDetectionTrainJob 删除后触发，删除关联的 MLflow 实验、运行和注册模型
    """
    logger.info(
        f"[Signal] post_delete 触发: AnomalyDetectionTrainJob (MLflow清理), "
        f"train_job_id={instance.id}, algorithm={instance.algorithm}"
    )

    def delete_mlflow_resources():
        try:
            # 构造实验和模型名称（与创建时一致）
            experiment_name = mlflow_service.build_experiment_name(
                prefix="AnomalyDetection",
                algorithm=instance.algorithm,
                train_job_id=instance.id,
            )
            model_name = mlflow_service.build_model_name(
                prefix="AnomalyDetection",
                algorithm=instance.algorithm,
                train_job_id=instance.id,
            )

            # 删除 MLflow 资源
            mlflow_service.delete_experiment_and_model(
                experiment_name=experiment_name, model_name=model_name
            )

            logger.info(
                f"成功删除 MLflow 资源: experiment={experiment_name}, model={model_name}, "
                f"train_job_id={instance.id}"
            )

        except Exception as e:
            # 不阻断删除流程，仅记录错误
            logger.error(
                f"删除 MLflow 资源失败 (不影响数据库删除): {str(e)}, "
                f"train_job_id={instance.id}, algorithm={instance.algorithm}",
                exc_info=True,
            )

    transaction.on_commit(delete_mlflow_resources)


@receiver(
    post_delete,
    sender=AnomalyDetectionServing,
    dispatch_uid="cleanup_ad_docker_container",
)
def cleanup_docker_container(sender, instance, **kwargs):
    """
    清理 Serving 服务的 Docker 容器

    在 AnomalyDetectionServing 删除后触发，停止并删除关联的 Docker 容器
    """
    logger.info(
        f"[Signal] post_delete 触发: AnomalyDetectionServing (容器清理), "
        f"serving_id={instance.id}, port={instance.port}"
    )

    def delete_container():
        try:
            # 构造容器 ID（与创建时一致）
            container_id = f"AnomalyDetection_Serving_{instance.id}"

            # 调用 webhookd API 删除容器
            result = WebhookClient.remove(container_id)

            logger.info(
                f"成功删除 Docker 容器: container_id={container_id}, "
                f"serving_id={instance.id}, result={result}"
            )

        except WebhookError as e:
            # 容器可能已不存在（手动删除、系统重启等），记录警告
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                logger.warning(
                    f"容器已不存在，跳过删除: container_id=AnomalyDetection_Serving_{instance.id}, "
                    f"serving_id={instance.id}"
                )
            else:
                logger.error(
                    f"删除 Docker 容器失败 (不影响数据库删除): {str(e)}, "
                    f"serving_id={instance.id}",
                    exc_info=True,
                )
        except Exception as e:
            logger.error(
                f"删除 Docker 容器失败 (不影响数据库删除): {str(e)}, "
                f"serving_id={instance.id}",
                exc_info=True,
            )

    transaction.on_commit(delete_container)
