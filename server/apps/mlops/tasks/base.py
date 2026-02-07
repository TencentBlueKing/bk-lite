"""
MLOps 任务通用工具函数
"""

from typing import Optional, Type

from django.db import models
from django.utils import timezone

from apps.core.logger import mlops_logger as logger


def mark_release_as_failed(
    release_model: Type[models.Model],
    release_id: int,
    error_message: Optional[str] = None,
) -> bool:
    """
    标记数据集发布记录为失败状态

    Args:
        release_model: 发布记录的 Django Model 类
            (e.g., AnomalyDetectionDatasetRelease, ClassificationDatasetRelease)
        release_id: 发布记录的主键 ID
        error_message: 可选的错误信息，如果提供则会存储到 metadata 中

    Returns:
        bool: 是否成功更新状态

    Example:
        from apps.mlops.models.classification import ClassificationDatasetRelease
        from apps.mlops.tasks.base import mark_release_as_failed

        mark_release_as_failed(ClassificationDatasetRelease, release_id)
        mark_release_as_failed(ClassificationDatasetRelease, release_id, "任务超时")
    """
    try:
        release = release_model.objects.get(id=release_id)
        release.status = "failed"

        update_fields = ["status"]

        if error_message:
            release.metadata = {
                "error": error_message,
                "failed_at": timezone.now().isoformat(),
            }
            update_fields.append("metadata")

        release.save(update_fields=update_fields)

        logger.info(
            f"标记发布记录为失败 - Model: {release_model.__name__}, "
            f"Release ID: {release_id}"
            + (f", 原因: {error_message}" if error_message else "")
        )
        return True

    except release_model.DoesNotExist:
        logger.error(
            f"发布记录不存在 - Model: {release_model.__name__}, Release ID: {release_id}"
        )
        return False

    except Exception as e:
        logger.error(
            f"标记失败状态时出错 - Model: {release_model.__name__}, "
            f"Release ID: {release_id}, Error: {str(e)}",
            exc_info=True,
        )
        return False
