"""
MLOps 信号处理器基础模块

提供通用的信号处理器工厂函数，用于统一注册各 ML 任务类型的资源清理信号
"""

from typing import Callable, Optional, Type

from django.db import models, transaction
from django.db.models.signals import post_delete
from django_minio_backend import MinioBackend

from apps.core.logger import mlops_logger as logger
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.webhook_client import WebhookClient, WebhookError


class MetadataDeleteStrategy:
    """元数据删除策略枚举"""

    NONE = "none"  # 没有 metadata 字段
    HASATTR = "hasattr"  # 使用 hasattr(instance.metadata, "delete")
    MINIO_BACKEND = "minio_backend"  # 使用 MinioBackend.delete()


def register_cleanup_signals(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    dataset_release_model: Type[models.Model],
    train_data_model: Type[models.Model],
    train_job_model: Type[models.Model],
    serving_model: Type[models.Model],
    metadata_strategy: str = MetadataDeleteStrategy.NONE,
    minio_bucket: str = "munchkin-public",
) -> None:
    """
    为 MLOps 模型注册资源清理信号处理器

    Args:
        prefix: 模型前缀，用于日志和资源命名 (如 "AnomalyDetection", "Classification")
        dispatch_uid_prefix: dispatch_uid 前缀 (如 "ad", "clf")
        dataset_release_model: 数据集发布模型类
        train_data_model: 训练数据模型类
        train_job_model: 训练任务模型类
        serving_model: 推理服务模型类
        metadata_strategy: 元数据删除策略 (MetadataDeleteStrategy)
        minio_bucket: MinIO bucket 名称 (仅 MINIO_BACKEND 策略需要)
    """
    # 1. 数据集发布文件清理
    _register_dataset_release_cleanup(
        prefix=prefix,
        dispatch_uid_prefix=dispatch_uid_prefix,
        model=dataset_release_model,
    )

    # 2. 训练数据文件清理
    _register_train_data_cleanup(
        prefix=prefix,
        dispatch_uid_prefix=dispatch_uid_prefix,
        model=train_data_model,
        metadata_strategy=metadata_strategy,
        minio_bucket=minio_bucket,
    )

    # 3. 训练任务配置文件清理
    _register_train_job_cleanup(
        prefix=prefix,
        dispatch_uid_prefix=dispatch_uid_prefix,
        model=train_job_model,
    )

    # 4. MLflow 资源清理
    _register_mlflow_cleanup(
        prefix=prefix,
        dispatch_uid_prefix=dispatch_uid_prefix,
        model=train_job_model,
    )

    # 5. Docker 容器清理
    _register_docker_cleanup(
        prefix=prefix,
        dispatch_uid_prefix=dispatch_uid_prefix,
        model=serving_model,
    )


def _register_dataset_release_cleanup(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    model: Type[models.Model],
) -> None:
    """注册数据集发布文件清理信号"""

    def cleanup_dataset_release_files(sender, instance, **kwargs):
        logger.info(
            f"[Signal] post_delete 触发: {prefix}DatasetRelease, "
            f"dataset_release_id={instance.id}, version={instance.version}, "
            f"has_dataset_file={bool(instance.dataset_file)}"
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

    post_delete.connect(
        cleanup_dataset_release_files,
        sender=model,
        dispatch_uid=f"cleanup_{dispatch_uid_prefix}_dataset_release",
    )


def _register_train_data_cleanup(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    model: Type[models.Model],
    metadata_strategy: str,
    minio_bucket: str,
) -> None:
    """注册训练数据文件清理信号"""

    def cleanup_train_data_files(sender, instance, **kwargs):
        has_metadata = hasattr(instance, "metadata") and bool(instance.metadata)
        logger.info(
            f"[Signal] post_delete 触发: {prefix}TrainData, "
            f"train_data_id={instance.id}, name={instance.name}, "
            f"has_train_data={bool(instance.train_data)}"
            + (f", has_metadata={has_metadata}" if metadata_strategy != MetadataDeleteStrategy.NONE else "")
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

                # 根据策略删除元数据
                if metadata_strategy == MetadataDeleteStrategy.HASATTR:
                    if instance.metadata:
                        try:
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
                elif metadata_strategy == MetadataDeleteStrategy.MINIO_BACKEND:
                    if instance.metadata:
                        storage = MinioBackend(bucket_name=minio_bucket)
                        storage.delete(instance.metadata)
                        logger.info(
                            f"成功删除元数据文件: {instance.metadata}, "
                            f"train_data_id={instance.id}, name={instance.name}"
                        )

                # 无文件时的日志
                if not instance.train_data and (
                    metadata_strategy == MetadataDeleteStrategy.NONE
                    or not (hasattr(instance, "metadata") and instance.metadata)
                ):
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

    post_delete.connect(
        cleanup_train_data_files,
        sender=model,
        dispatch_uid=f"cleanup_{dispatch_uid_prefix}_train_data",
    )


def _register_train_job_cleanup(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    model: Type[models.Model],
) -> None:
    """注册训练任务配置文件清理信号"""

    def cleanup_train_job_config_file(sender, instance, **kwargs):
        logger.info(
            f"[Signal] post_delete 触发: {prefix}TrainJob, "
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

    post_delete.connect(
        cleanup_train_job_config_file,
        sender=model,
        dispatch_uid=f"cleanup_{dispatch_uid_prefix}_train_job",
    )


def _register_mlflow_cleanup(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    model: Type[models.Model],
) -> None:
    """注册 MLflow 资源清理信号"""

    def cleanup_mlflow_experiment(sender, instance, **kwargs):
        logger.info(
            f"[Signal] post_delete 触发: {prefix}TrainJob (MLflow清理), "
            f"train_job_id={instance.id}, algorithm={instance.algorithm}"
        )

        def delete_mlflow_resources():
            try:
                experiment_name = mlflow_service.build_experiment_name(
                    prefix=prefix,
                    algorithm=instance.algorithm,
                    train_job_id=instance.id,
                )
                model_name = mlflow_service.build_model_name(
                    prefix=prefix,
                    algorithm=instance.algorithm,
                    train_job_id=instance.id,
                )

                mlflow_service.delete_experiment_and_model(
                    experiment_name=experiment_name, model_name=model_name
                )

                logger.info(
                    f"成功删除 MLflow 资源: experiment={experiment_name}, model={model_name}, "
                    f"train_job_id={instance.id}"
                )

            except Exception as e:
                logger.error(
                    f"删除 MLflow 资源失败 (不影响数据库删除): {str(e)}, "
                    f"train_job_id={instance.id}, algorithm={instance.algorithm}",
                    exc_info=True,
                )

        transaction.on_commit(delete_mlflow_resources)

    post_delete.connect(
        cleanup_mlflow_experiment,
        sender=model,
        dispatch_uid=f"cleanup_{dispatch_uid_prefix}_mlflow_experiment",
    )


def _register_docker_cleanup(
    *,
    prefix: str,
    dispatch_uid_prefix: str,
    model: Type[models.Model],
) -> None:
    """注册 Docker 容器清理信号"""

    def cleanup_docker_container(sender, instance, **kwargs):
        logger.info(
            f"[Signal] post_delete 触发: {prefix}Serving (容器清理), "
            f"serving_id={instance.id}, port={instance.port}"
        )

        def delete_container():
            try:
                container_id = f"{prefix}_Serving_{instance.id}"
                result = WebhookClient.remove(container_id)

                logger.info(
                    f"成功删除 Docker 容器: container_id={container_id}, "
                    f"serving_id={instance.id}, result={result}"
                )

            except WebhookError as e:
                if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                    logger.warning(
                        f"容器已不存在，跳过删除: container_id={prefix}_Serving_{instance.id}, "
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

    post_delete.connect(
        cleanup_docker_container,
        sender=model,
        dispatch_uid=f"cleanup_{dispatch_uid_prefix}_docker_container",
    )
