"""
MLOps 任务通用工具函数
"""

import codecs
import json
import math
import os
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import timedelta
from itertools import chain
from pathlib import Path
from typing import Any, Callable, Optional, Type

from django.apps import apps as django_apps
from django.core.files import File
from django.core.files.utils import validate_file_name
from django.db import models, transaction
from django.utils import timezone
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.logger import mlops_logger as logger
from apps.mlops.constants import DatasetReleaseStatus
from apps.mlops.models.dataset_release_execution import DatasetReleaseExecution, DatasetReleaseObjectCleanup

_EXECUTION_MODE_ENV = "MLOPS_DATASET_RELEASE_EXECUTION_MODE"
_LEASE_SECONDS_ENV = "MLOPS_DATASET_RELEASE_LEASE_SECONDS"
_DEFAULT_LEASE_SECONDS = 7500
_MIN_LEASE_SECONDS = 7320
_MAX_RETRY_SECONDS = 300
_CLEANUP_LEASE_SECONDS = 300
_CLEANUP_BATCH_SIZE = 1000
_TERMINAL_RELEASE_STATUSES = {
    DatasetReleaseStatus.PUBLISHED,
    DatasetReleaseStatus.FAILED,
    DatasetReleaseStatus.ARCHIVED,
}


@dataclass(frozen=True)
class DatasetReleaseClaim:
    release: models.Model
    acquired: bool
    owner_token: Optional[str]
    reason: Optional[str] = None
    stale_object_paths: tuple[str, ...] = ()

    @property
    def stale_object_path(self) -> Optional[str]:
        return self.stale_object_paths[0] if self.stale_object_paths else None


class DatasetReleaseBusy(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Dataset release lease is active; retry after {retry_after}s")


@dataclass
class DatasetReleaseAttempt:
    """把本次任务候选 token 与实际领取 token 传回异常收口路径。"""

    candidate_token: str = field(default_factory=lambda: uuid.uuid4().hex)
    owner_token: Optional[str] = None
    mode: str = field(default_factory=lambda: get_dataset_release_execution_mode())
    claimed: bool = False

    def can_mark_failure(self) -> bool:
        return self.mode == "shadow" or self.claimed


@dataclass(frozen=True)
class DatasetReleaseObjectCleanupClaim:
    intent_id: int
    cleanup_token: str
    object_path: str


def get_dataset_release_execution_mode() -> str:
    mode = os.getenv(_EXECUTION_MODE_ENV, "shadow").strip().lower()
    if mode not in {"shadow", "enforce"}:
        logger.warning(
            "数据集发布执行模式无效，回退 shadow - value=%s",
            mode,
        )
        return "shadow"
    return mode


def _get_dataset_release_lease_seconds() -> int:
    configured = os.getenv(_LEASE_SECONDS_ENV, str(_DEFAULT_LEASE_SECONDS))
    try:
        lease_seconds = int(configured)
    except (TypeError, ValueError):
        lease_seconds = _DEFAULT_LEASE_SECONDS
    return max(_MIN_LEASE_SECONDS, lease_seconds)


def _release_type(release_model: Type[models.Model]) -> str:
    return release_model._meta.label_lower


def _retry_after(lease_expires_at) -> int:
    remaining = math.ceil((lease_expires_at - timezone.now()).total_seconds())
    return min(_MAX_RETRY_SECONDS, max(1, remaining))


def claim_dataset_release(
    release_model: Type[models.Model],
    release_id: int,
    owner_token: Optional[str] = None,
    *,
    attempt: Optional[DatasetReleaseAttempt] = None,
) -> DatasetReleaseClaim:
    """短事务领取发布任务；enforce 模式下持久化租约与执行归属。"""

    mode = get_dataset_release_execution_mode()
    token = owner_token or (attempt.candidate_token if attempt else uuid.uuid4().hex)
    busy_retry_after = None
    if attempt is not None:
        attempt.mode = mode
        attempt.owner_token = None
        attempt.claimed = False

    with transaction.atomic():
        release = release_model.objects.select_for_update().get(id=release_id)
        release_type = _release_type(release_model)

        if release.status in _TERMINAL_RELEASE_STATUSES:
            execution = DatasetReleaseExecution.objects.select_for_update().filter(release_type=release_type, release_id=release_id).first()
            stale_object_paths = tuple(
                DatasetReleaseObjectCleanup.objects.select_for_update()
                .filter(release_type=release_type, release_id=release_id)
                .values_list("object_path", flat=True)
                .order_by("id")[:_CLEANUP_BATCH_SIZE]
            )
            if execution is not None:
                execution.delete()
            return DatasetReleaseClaim(
                release=release,
                acquired=False,
                owner_token=None,
                reason=f"Task already {release.status}",
                stale_object_paths=stale_object_paths,
            )

        if mode == "shadow":
            if release.status == "processing":
                logger.warning(
                    "数据集发布重复领取 shadow 命中 - Model: %s, Release ID: %s",
                    release_model.__name__,
                    release_id,
                )
            release.status = DatasetReleaseStatus.PROCESSING
            release.save(update_fields=["status"])
            if attempt is not None:
                attempt.claimed = True
            return DatasetReleaseClaim(
                release=release,
                acquired=True,
                owner_token=None,
            )

        current_time = timezone.now()
        lease_until = current_time + timedelta(seconds=_get_dataset_release_lease_seconds())
        execution = DatasetReleaseExecution.objects.select_for_update().filter(release_type=release_type, release_id=release_id).first()

        if release.status == DatasetReleaseStatus.PROCESSING and execution is None:
            execution = DatasetReleaseExecution.objects.create(
                release_type=release_type,
                release_id=release_id,
                owner_token="",
                lease_expires_at=lease_until,
                attempt=0,
            )
            busy_retry_after = _retry_after(execution.lease_expires_at)
        elif release.status == DatasetReleaseStatus.PROCESSING and execution.lease_expires_at > current_time:
            busy_retry_after = _retry_after(execution.lease_expires_at)
        else:
            if execution is None:
                execution = DatasetReleaseExecution(
                    release_type=release_type,
                    release_id=release_id,
                )
            stale_object_paths = tuple(
                DatasetReleaseObjectCleanup.objects.select_for_update()
                .filter(release_type=release_type, release_id=release_id)
                .exclude(owner_token=token)
                .values_list("object_path", flat=True)
                .order_by("id")[:_CLEANUP_BATCH_SIZE]
            )
            execution.owner_token = token
            execution.lease_expires_at = lease_until
            execution.attempt += 1
            execution.save()
            release.status = DatasetReleaseStatus.PROCESSING
            release.save(update_fields=["status"])

    if busy_retry_after is not None:
        raise DatasetReleaseBusy(retry_after=busy_retry_after)

    if attempt is not None:
        attempt.owner_token = token
        attempt.claimed = True
    return DatasetReleaseClaim(
        release=release,
        acquired=True,
        owner_token=token,
        stale_object_paths=stale_object_paths,
    )


def record_dataset_release_object_path(
    release_model: Type[models.Model],
    release_id: int,
    owner_token: str,
    object_path: str,
) -> bool:
    """持久化补偿路径；enforce 校验 owner，shadow 登记实际保存路径。"""

    with transaction.atomic():
        release = release_model.objects.select_for_update().filter(id=release_id).first()
        mode = get_dataset_release_execution_mode()
        execution = (
            DatasetReleaseExecution.objects.select_for_update()
            .filter(
                release_type=_release_type(release_model),
                release_id=release_id,
                owner_token=owner_token,
            )
            .first()
        )
        current_time = timezone.now()
        if execution is None and mode == "shadow":
            DatasetReleaseObjectCleanup.objects.update_or_create(
                release_type=_release_type(release_model),
                release_id=release_id,
                owner_token=owner_token,
                defaults={
                    "object_path": object_path,
                    "cleanup_token": owner_token,
                    "cleanup_lease_expires_at": current_time + timedelta(seconds=_get_dataset_release_lease_seconds()),
                },
            )
            return True
        if release is None:
            if execution is not None:
                execution.delete()
            return False
        if release.status != DatasetReleaseStatus.PROCESSING:
            return False
        if execution.lease_expires_at <= current_time:
            return False
        execution.lease_expires_at = current_time + timedelta(seconds=_get_dataset_release_lease_seconds())
        execution.save(update_fields=["lease_expires_at"])
        DatasetReleaseObjectCleanup.objects.update_or_create(
            release_type=_release_type(release_model),
            release_id=release_id,
            owner_token=owner_token,
            defaults={"object_path": object_path},
        )
        return True


def finalize_dataset_release(
    release_model: Type[models.Model],
    release_id: int,
    owner_token: Optional[str],
    *,
    file_size: int,
    metadata: dict[str, Any],
    saved_path: str,
    cleanup_owner_token: Optional[str] = None,
) -> bool:
    """仅允许当前执行者发布结果；shadow 调用维持旧无 token 行为。"""

    if owner_token is None:
        with transaction.atomic():
            release = release_model.objects.select_for_update().get(id=release_id)
            execution = (
                DatasetReleaseExecution.objects.select_for_update()
                .filter(
                    release_type=_release_type(release_model),
                    release_id=release_id,
                )
                .first()
            )
            if release.status == DatasetReleaseStatus.ARCHIVED:
                if execution is not None:
                    execution.delete()
                return False
            release.status = DatasetReleaseStatus.PUBLISHED
            release.file_size = file_size
            release.metadata = metadata
            release.dataset_file.name = saved_path
            release.save(update_fields=["status", "file_size", "metadata", "dataset_file"])
            if cleanup_owner_token is not None:
                DatasetReleaseObjectCleanup.objects.filter(
                    release_type=_release_type(release_model),
                    release_id=release_id,
                    owner_token=cleanup_owner_token,
                ).delete()
            if execution is not None:
                execution.delete()
        return True

    release_type = _release_type(release_model)
    with transaction.atomic():
        release = release_model.objects.select_for_update().filter(id=release_id).first()
        execution = (
            DatasetReleaseExecution.objects.select_for_update()
            .filter(
                release_type=release_type,
                release_id=release_id,
                owner_token=owner_token,
            )
            .first()
        )
        if execution is None:
            return False
        if release is None:
            execution.delete()
            return False
        if release.status != DatasetReleaseStatus.PROCESSING:
            execution.delete()
            return False
        if execution.lease_expires_at <= timezone.now():
            return False
        release.status = DatasetReleaseStatus.PUBLISHED
        release.file_size = file_size
        release.metadata = metadata
        release.dataset_file.name = saved_path
        release.save(update_fields=["status", "file_size", "metadata", "dataset_file"])
        DatasetReleaseObjectCleanup.objects.filter(
            release_type=release_type,
            release_id=release_id,
            owner_token=owner_token,
        ).delete()
        execution.delete()
        return True


def build_publish_object_name(filename: str, owner_token: Optional[str]) -> str:
    if owner_token is None:
        return filename
    path = Path(filename)
    return f"{path.stem}_{owner_token}{path.suffix}"


def delete_stale_publish_object(storage, saved_path: str) -> bool:
    try:
        storage.delete(saved_path)
        return True
    except Exception as exc:
        logger.error(
            "清理陈旧数据集发布对象失败 - path=%s error_type=%s",
            saved_path,
            exc.__class__.__name__,
        )
        return False


def cleanup_claim_stale_object(storage, claim: DatasetReleaseClaim) -> None:
    for object_path in claim.stale_object_paths:
        if delete_stale_publish_object(storage, object_path):
            DatasetReleaseObjectCleanup.objects.filter(object_path=object_path).delete()


def prepare_claim_storage(claim: DatasetReleaseClaim):
    """清理领取时发现的旧对象；终态补偿失败不反向改写业务终态。"""

    if not claim.stale_object_paths:
        return None
    try:
        storage = MinioBackend(
            bucket_name="munchkin-public",
            replace_existing=claim.owner_token is not None,
        )
    except Exception as exc:
        if claim.acquired:
            raise
        logger.error(
            "终态数据集发布对象补偿暂不可用 - error_type=%s",
            exc.__class__.__name__,
        )
        return None
    cleanup_claim_stale_object(storage, claim)
    return storage


def cleanup_release_object_intents(
    storage,
    release_model: Type[models.Model],
    release_id: int,
    *,
    owner_token: Optional[str] = None,
) -> bool:
    intents = DatasetReleaseObjectCleanup.objects.filter(
        release_type=_release_type(release_model),
        release_id=release_id,
    )
    if owner_token is not None:
        intents = intents.filter(owner_token=owner_token)
    all_cleaned = True
    intent_batch = list(intents.order_by("id")[: _CLEANUP_BATCH_SIZE + 1])
    all_cleaned = len(intent_batch) <= _CLEANUP_BATCH_SIZE
    for intent in intent_batch[:_CLEANUP_BATCH_SIZE]:
        if delete_stale_publish_object(storage, intent.object_path):
            intent.delete()
        else:
            all_cleaned = False
    return all_cleaned


def inspect_dataset_release_object_cleanup(intent_id: int) -> tuple[str, str]:
    """只读预检一个补偿意图；结果仅描述当前快照。"""

    intent = DatasetReleaseObjectCleanup.objects.filter(id=intent_id).values().first()
    if intent is None:
        return "missing", ""
    current_time = timezone.now()
    if intent["cleanup_token"] and intent["cleanup_lease_expires_at"] is not None and intent["cleanup_lease_expires_at"] > current_time:
        return "skip_claimed", intent["object_path"]
    release_model = django_apps.get_model(intent["release_type"])
    release = release_model.objects.filter(id=intent["release_id"]).first()
    referenced_path = getattr(getattr(release, "dataset_file", None), "name", "")
    if referenced_path == intent["object_path"]:
        return "discard_referenced_intent", intent["object_path"]
    execution = DatasetReleaseExecution.objects.filter(
        release_type=intent["release_type"],
        release_id=intent["release_id"],
        owner_token=intent["owner_token"],
        lease_expires_at__gt=current_time,
    ).first()
    return ("skip_active" if execution is not None else "delete"), intent["object_path"]


def claim_dataset_release_object_cleanup(
    intent_id: int,
    cleanup_token: Optional[str] = None,
) -> Optional[DatasetReleaseObjectCleanupClaim]:
    """在固定锁序下 fence 过期 owner，并领取一个持久对象补偿意图。"""

    snapshot = DatasetReleaseObjectCleanup.objects.filter(id=intent_id).values("release_type", "release_id", "owner_token", "object_path").first()
    if snapshot is None:
        return None
    release_model = django_apps.get_model(snapshot["release_type"])
    token = cleanup_token or uuid.uuid4().hex
    current_time = timezone.now()

    with transaction.atomic():
        release = release_model.objects.select_for_update().filter(id=snapshot["release_id"]).first()
        execution = (
            DatasetReleaseExecution.objects.select_for_update()
            .filter(
                release_type=snapshot["release_type"],
                release_id=snapshot["release_id"],
            )
            .first()
        )
        intent = DatasetReleaseObjectCleanup.objects.select_for_update().filter(id=intent_id, **snapshot).first()
        if intent is None:
            return None
        referenced_path = getattr(getattr(release, "dataset_file", None), "name", "")
        if referenced_path == intent.object_path:
            intent.delete()
            return None
        if intent.cleanup_token and intent.cleanup_lease_expires_at is not None and intent.cleanup_lease_expires_at > current_time:
            return None
        if execution is not None and execution.owner_token == intent.owner_token:
            if execution.lease_expires_at > current_time:
                return None
            execution.delete()

        intent.cleanup_token = token
        intent.cleanup_lease_expires_at = current_time + timedelta(seconds=_CLEANUP_LEASE_SECONDS)
        intent.save(update_fields=["cleanup_token", "cleanup_lease_expires_at"])
        return DatasetReleaseObjectCleanupClaim(
            intent_id=intent.id,
            cleanup_token=token,
            object_path=intent.object_path,
        )


def complete_dataset_release_object_cleanup(
    claim: DatasetReleaseObjectCleanupClaim,
    *,
    cleaned: bool,
) -> bool:
    """仅凭当前 cleanup token 消费意图；失败时释放领取供后续重试。"""

    with transaction.atomic():
        intent = DatasetReleaseObjectCleanup.objects.select_for_update().filter(id=claim.intent_id, cleanup_token=claim.cleanup_token).first()
        if intent is None:
            return False
        if cleaned:
            intent.delete()
        else:
            intent.cleanup_token = ""
            intent.cleanup_lease_expires_at = None
            intent.save(update_fields=["cleanup_token", "cleanup_lease_expires_at"])
        return True


def save_dataset_release_object(
    storage,
    content,
    requested_path: str,
    release_model: Type[models.Model],
    release_id: int,
    owner_token: Optional[str],
    cleanup_owner_token: str,
) -> Optional[str]:
    """在对象写入前持久化实际路径；shadow 沿用 Storage 的旧名称分配。"""

    saved_candidate = requested_path if owner_token is not None else storage.get_available_name(requested_path)
    if not record_dataset_release_object_path(
        release_model,
        release_id,
        cleanup_owner_token,
        saved_candidate,
    ):
        return None
    if owner_token is None:
        # get_available_name 已完成旧 shadow 的名称分配；直接保存该保留路径，避免二次分配造成 intent 漂移。
        if not hasattr(content, "chunks"):
            content = File(content, saved_candidate)
        validate_file_name(saved_candidate, allow_relative_path=True)
        saved_path = storage._save(saved_candidate, content)
        validate_file_name(saved_path, allow_relative_path=True)
        return saved_path
    return storage.save(saved_candidate, content)


def finalize_uploaded_dataset_release(
    storage,
    saved_path: str,
    release_model: Type[models.Model],
    release_id: int,
    owner_token: Optional[str],
    *,
    file_size: int,
    metadata: dict[str, Any],
    cleanup_owner_token: Optional[str] = None,
) -> bool:
    """提交已上传对象；提交失败或 owner 陈旧时回收本次对象。"""

    try:
        finalized = finalize_dataset_release(
            release_model,
            release_id,
            owner_token,
            file_size=file_size,
            metadata=metadata,
            saved_path=saved_path,
            cleanup_owner_token=cleanup_owner_token,
        )
    except Exception:
        if owner_token is not None and cleanup_owner_token is not None:
            cleanup_release_object_intents(
                storage,
                release_model,
                release_id,
                owner_token=cleanup_owner_token,
            )
        raise
    if not finalized and owner_token is not None and cleanup_owner_token is not None:
        cleanup_release_object_intents(
            storage,
            release_model,
            release_id,
            owner_token=cleanup_owner_token,
        )
    elif finalized and owner_token is not None:
        cleanup_release_object_intents(storage, release_model, release_id)
    return finalized


def get_storage_display_url(storage, saved_path: str) -> str:
    """URL 仅用于日志，不让展示信息失败回滚已提交发布。"""

    try:
        return storage.url(saved_path)
    except Exception as exc:
        logger.warning(
            "获取数据集发布对象 URL 失败 - path=%s error_type=%s",
            saved_path,
            exc.__class__.__name__,
        )
        return saved_path


def mark_release_as_failed(
    release_model: Type[models.Model],
    release_id: int,
    error_message: Optional[str] = None,
    *,
    owner_token: Optional[str] = None,
    cleanup_owner_token: Optional[str] = None,
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
        updated = False
        with transaction.atomic():
            release = release_model.objects.select_for_update().filter(id=release_id).first()
            execution = (
                DatasetReleaseExecution.objects.select_for_update()
                .filter(
                    release_type=_release_type(release_model),
                    release_id=release_id,
                )
                .first()
            )
            if owner_token is not None:
                if release is None:
                    if execution is not None:
                        execution.delete()
                    logger.error(
                        "发布记录不存在 - Model: %s, Release ID: %s",
                        release_model.__name__,
                        release_id,
                    )
                elif (
                    execution is not None
                    and execution.owner_token == owner_token
                    and release.status == DatasetReleaseStatus.PROCESSING
                    and execution.lease_expires_at > timezone.now()
                ):
                    updated = True
                elif execution is not None and execution.owner_token == owner_token and release.status != DatasetReleaseStatus.PROCESSING:
                    execution.delete()
            elif release is None:
                if execution is not None:
                    execution.delete()
                logger.error(
                    "发布记录不存在 - Model: %s, Release ID: %s",
                    release_model.__name__,
                    release_id,
                )
            elif release.status != DatasetReleaseStatus.ARCHIVED:
                updated = True
            elif execution is not None:
                execution.delete()

            if updated:
                release.status = DatasetReleaseStatus.FAILED
                update_fields = ["status"]
                if error_message:
                    release.metadata = {
                        "error": error_message,
                        "failed_at": timezone.now().isoformat(),
                    }
                    update_fields.append("metadata")
                release.save(update_fields=update_fields)
                if execution is not None:
                    execution.delete()

        cleanup_intents = DatasetReleaseObjectCleanup.objects.filter(
            release_type=_release_type(release_model),
            release_id=release_id,
        )
        cleanup_token = cleanup_owner_token or owner_token
        if cleanup_token is not None:
            cleanup_intents = cleanup_intents.filter(owner_token=cleanup_token)
        if owner_token is not None and cleanup_intents.exists():
            try:
                cleanup_release_object_intents(
                    MinioBackend(bucket_name="munchkin-public"),
                    release_model,
                    release_id,
                    owner_token=cleanup_token,
                )
            except Exception as exc:
                logger.error(
                    "失败终态对象补偿暂不可用 - Release ID: %s error_type=%s",
                    release_id,
                    exc.__class__.__name__,
                )

        if updated:
            logger.info(
                f"标记发布记录为失败 - Model: {release_model.__name__}, " f"Release ID: {release_id}" + (f", 原因: {error_message}" if error_message else "")
            )
        return updated

    except release_model.DoesNotExist:
        logger.error(f"发布记录不存在 - Model: {release_model.__name__}, Release ID: {release_id}")
        return False

    except Exception as e:
        logger.error(
            f"标记失败状态时出错 - Model: {release_model.__name__}, " f"Release ID: {release_id}, Error: {str(e)}",
            exc_info=True,
        )
        return False


_MAX_STREAM_CHUNK_SIZE = 65536


def _get_stream_chunk_size() -> int:
    """读取流式块大小，并将单次读取限制在 64 KB 内。"""
    configured_size = int(os.getenv("MLOPS_STREAM_CHUNK_SIZE", _MAX_STREAM_CHUNK_SIZE))
    return min(_MAX_STREAM_CHUNK_SIZE, max(1, configured_size))


_STREAM_CHUNK_SIZE = _get_stream_chunk_size()  # 可通过环境变量调整，默认 64 KB
_SAMPLE_COUNT_ALGORITHM = "logical_records_v1_legacy_fallback"


@dataclass
class DatasetPublishConfig:
    """
    数据集发布任务的配置

    用于配置不同类型数据集发布任务的差异化参数，实现代码复用。

    Attributes:
        release_model: 发布记录的 Django Model 类
        train_data_model: 训练数据的 Django Model 类
        task_type: 任务类型标识，用于日志和存储路径 (e.g., "classification", "timeseries")
        file_extension: 数据文件扩展名 (e.g., "csv", "txt")
        storage_prefix: MinIO 存储路径前缀 (e.g., "classification_datasets")
        count_samples: 样本计数函数，接收本地文件 Path，流式返回样本数
        build_metadata: 元数据构建函数，用于生成数据集元信息
    """

    release_model: Type[models.Model]
    train_data_model: Type[models.Model]
    task_type: str
    file_extension: str
    storage_prefix: str
    count_samples: Callable[[Path], int]
    build_metadata: Callable[..., dict[str, Any]]


def count_csv_samples(file_path: Path) -> int:
    """CSV 文件样本计数：按固定字节块统计表头后的逻辑记录。"""
    record_count = 0
    record_has_content = False
    at_field_start = True
    in_quotes = False
    after_quote = False
    skip_lf_after_cr = False
    legacy_newline_count = 0
    malformed = False

    def finish_record() -> None:
        nonlocal record_count, record_has_content, at_field_start
        if record_has_content:
            record_count += 1
        record_has_content = False
        at_field_start = True

    with open(file_path, "rb") as csv_file:
        prefix = csv_file.read(3)
        if prefix == b"\xef\xbb\xbf":
            prefix = b""

        for chunk in chain(
            (prefix,),
            iter(lambda: csv_file.read(_STREAM_CHUNK_SIZE), b""),
        ):
            legacy_newline_count += chunk.count(b"\n")
            for byte in chunk:
                if malformed:
                    continue

                if skip_lf_after_cr:
                    skip_lf_after_cr = False
                    if byte == ord("\n"):
                        continue

                if in_quotes:
                    if byte == ord('"'):
                        in_quotes = False
                        after_quote = True
                    continue

                if after_quote:
                    if byte == ord('"'):
                        in_quotes = True
                        after_quote = False
                    elif byte == ord(","):
                        record_has_content = True
                        at_field_start = True
                        after_quote = False
                    elif byte in (ord("\r"), ord("\n")):
                        finish_record()
                        after_quote = False
                        skip_lf_after_cr = byte == ord("\r")
                    elif byte in b" \t":
                        continue
                    else:
                        malformed = True
                    continue

                if byte == ord(","):
                    record_has_content = True
                    at_field_start = True
                elif byte in (ord("\r"), ord("\n")):
                    finish_record()
                    skip_lf_after_cr = byte == ord("\r")
                elif byte == ord('"') and at_field_start:
                    record_has_content = True
                    at_field_start = False
                    in_quotes = True
                else:
                    at_field_start = False
                    if byte not in b" \t\v\f":
                        record_has_content = True

    if in_quotes:
        malformed = True
    if malformed:
        return max(0, legacy_newline_count - 1)
    if record_has_content:
        record_count += 1
    return max(0, record_count - 1)


def count_txt_samples(file_path: Path) -> int:
    """TXT 文件样本计数：非空行数，流式按块读取避免全量加载"""
    sample_count = 0
    line_has_content = False
    skip_lf_after_cr = False
    decoder = codecs.getincrementaldecoder("utf-8")(errors="surrogateescape")

    def consume(chars: str) -> None:
        nonlocal sample_count, line_has_content, skip_lf_after_cr
        for char in chars:
            if skip_lf_after_cr:
                skip_lf_after_cr = False
                if char == "\n":
                    continue

            if char in "\r\n":
                if line_has_content:
                    sample_count += 1
                line_has_content = False
                skip_lf_after_cr = char == "\r"
            elif not char.isspace():
                line_has_content = True

    with open(file_path, "rb") as text_file:
        for chunk in iter(lambda: text_file.read(_STREAM_CHUNK_SIZE), b""):
            consume(decoder.decode(chunk))
        consume(decoder.decode(b"", final=True))

    return sample_count + int(line_has_content)


def build_base_metadata(
    train_samples: int,
    val_samples: int,
    test_samples: int,
    train_obj: Any,
    val_obj: Any,
    test_obj: Any,
    train_file_id: int,
    val_file_id: int,
    test_file_id: int,
    extra_fields: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    构建基础数据集元信息

    Args:
        train_samples: 训练集样本数
        val_samples: 验证集样本数
        test_samples: 测试集样本数
        train_obj: 训练数据对象
        val_obj: 验证数据对象
        test_obj: 测试数据对象
        train_file_id: 训练文件 ID
        val_file_id: 验证文件 ID
        test_file_id: 测试文件 ID
        extra_fields: 额外的元数据字段

    Returns:
        完整的元数据字典
    """
    total_samples = train_samples + val_samples + test_samples
    metadata: dict[str, Any] = {
        "train_samples": train_samples,
        "val_samples": val_samples,
        "test_samples": test_samples,
        "total_samples": total_samples,
        "sample_count_algorithm": _SAMPLE_COUNT_ALGORITHM,
    }
    if extra_fields:
        metadata.update(extra_fields)
    metadata["source"] = {
        "type": "manual_selection",
        "train_file_id": train_file_id,
        "val_file_id": val_file_id,
        "test_file_id": test_file_id,
        "train_file_name": train_obj.name,
        "val_file_name": val_obj.name,
        "test_file_name": test_obj.name,
    }
    return metadata


def publish_dataset_release_base(
    config: DatasetPublishConfig,
    release_id: int,
    train_file_id: int,
    val_file_id: int,
    test_file_id: int,
    *,
    owner_token: Optional[str] = None,
    attempt: Optional[DatasetReleaseAttempt] = None,
) -> dict[str, Any]:
    """
    数据集发布的通用基础逻辑

    此函数封装了所有数据集发布任务的共通流程：
    1. 获取并锁定发布记录
    2. 检查状态防止重复执行
    3. 下载训练/验证/测试数据文件
    4. 统计样本数
    5. 生成元数据
    6. 打包为 ZIP 并上传到 MinIO
    7. 更新发布记录

    Args:
        config: 数据集发布配置
        release_id: 发布记录 ID
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果，包含 result (bool), release_id 等字段

    Raises:
        Exception: 发布过程中的任何异常（调用方需处理）
    """
    release_model = config.release_model
    train_data_model = config.train_data_model

    claim = claim_dataset_release(
        release_model,
        release_id,
        owner_token,
        attempt=attempt,
    )
    storage = prepare_claim_storage(claim)
    if not claim.acquired:
        logger.info(
            "任务未领取 - Release ID: %s, 原因: %s",
            release_id,
            claim.reason,
        )
        return {"result": False, "reason": claim.reason}

    release = claim.release
    execution_token = claim.owner_token
    cleanup_owner_token = execution_token or (attempt.candidate_token if attempt else uuid.uuid4().hex)
    if storage is None:
        storage = MinioBackend(
            bucket_name="munchkin-public",
            replace_existing=execution_token is not None,
        )

    dataset = release.dataset
    version = release.version

    # 获取训练数据对象
    train_obj = train_data_model.objects.get(id=train_file_id, dataset=dataset)
    val_obj = train_data_model.objects.get(id=val_file_id, dataset=dataset)
    test_obj = train_data_model.objects.get(id=test_file_id, dataset=dataset)

    logger.info(f"开始发布{config.task_type}数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}")

    # 创建临时目录用于存放文件
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # 文件配置
        ext = config.file_extension
        files_info = [
            (train_obj.train_data, f"train_data.{ext}", "train"),
            (val_obj.train_data, f"val_data.{ext}", "val"),
            (test_obj.train_data, f"test_data.{ext}", "test"),
        ]

        # 统计数据集信息
        sample_counts: dict[str, int] = {"train": 0, "val": 0, "test": 0}

        for file_field, filename, data_type in files_info:
            if file_field and file_field.name:
                # 流式将 MinIO 文件写入本地临时目录，避免全量加载入内存
                local_file_path = temp_path / filename
                with file_field.open("rb") as src, open(local_file_path, "wb") as dst:
                    for chunk in iter(lambda: src.read(_STREAM_CHUNK_SIZE), b""):
                        dst.write(chunk)

                file_size = local_file_path.stat().st_size

                # 样本计数从本地文件流式读取
                sample_count = config.count_samples(local_file_path)
                sample_counts[data_type] = sample_count

                logger.info(f"下载文件成功: {filename}, 大小: {file_size} bytes, 样本数: {sample_count}")

        train_samples = sample_counts["train"]
        val_samples = sample_counts["val"]
        test_samples = sample_counts["test"]

        # 生成数据集元信息
        dataset_metadata = config.build_metadata(
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

        # 保存数据集元信息到临时文件
        metadata_file = temp_path / "dataset_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(dataset_metadata, f, ensure_ascii=False, indent=2)

        # 创建 ZIP 压缩包
        zip_filename = f"{config.task_type}_dataset_{dataset.name}_{version}.zip"
        zip_path = temp_path / zip_filename

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in temp_path.iterdir():
                if file_path != zip_path:
                    zipf.write(file_path, file_path.name)

        zip_size = zip_path.stat().st_size
        zip_size_mb = zip_size / 1024 / 1024
        logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

        # 上传 ZIP 文件到 MinIO
        with open(zip_path, "rb") as f:
            object_name = build_publish_object_name(zip_filename, execution_token)
            date_prefixed_path = iso_date_prefix(dataset, object_name)
            zip_object_path = f"{config.storage_prefix}/{dataset.id}/{date_prefixed_path}"

            saved_path = save_dataset_release_object(
                storage,
                f,
                zip_object_path,
                release_model,
                release_id,
                execution_token,
                cleanup_owner_token,
            )
            if saved_path is None:
                logger.warning("数据集发布上传前 owner 已失效 - Release ID: %s", release_id)
                return {"result": False, "reason": "Stale execution"}
        finalized = finalize_uploaded_dataset_release(
            storage,
            saved_path,
            release_model,
            release_id,
            execution_token,
            file_size=zip_size,
            metadata=dataset_metadata,
            cleanup_owner_token=cleanup_owner_token,
        )
        if not finalized:
            logger.warning("陈旧数据集发布结果已丢弃 - Release ID: %s", release_id)
            return {"result": False, "reason": "Stale execution"}

        zip_url = get_storage_display_url(storage, saved_path)
        logger.info(f"数据集上传成功: {zip_url}")

        logger.info(f"{config.task_type}数据集发布成功 - Release ID: {release.id}, 样本数: {train_samples}/{val_samples}/{test_samples}")

        return {"result": True, "release_id": release_id}
