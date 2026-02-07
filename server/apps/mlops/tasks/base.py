"""
MLOps 任务通用工具函数
"""

import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Type

from django.db import models, transaction
from django.utils import timezone
from django_minio_backend import MinioBackend, iso_date_prefix

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
        count_samples: 样本计数函数，接收文件内容(bytes)，返回样本数
        build_metadata: 元数据构建函数，用于生成数据集元信息
    """

    release_model: Type[models.Model]
    train_data_model: Type[models.Model]
    task_type: str
    file_extension: str
    storage_prefix: str
    count_samples: Callable[[bytes], int]
    build_metadata: Callable[..., dict[str, Any]]


def count_csv_samples(content: bytes) -> int:
    """CSV 文件样本计数：行数 - 1（去掉表头）"""
    line_count = content.decode("utf-8").count("\n")
    return max(0, line_count - 1)


def count_txt_samples(content: bytes) -> int:
    """TXT 文件样本计数：非空行数"""
    text = content.decode("utf-8").strip()
    if not text:
        return 0
    return text.count("\n") + 1


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

    # 使用行锁防止并发执行
    with transaction.atomic():
        release = release_model.objects.select_for_update().get(id=release_id)

        # 防止重复执行：检查当前状态
        if release.status in ["published", "failed"]:
            logger.info(
                f"任务已结束 - Release ID: {release_id}, 状态: {release.status}, 跳过执行"
            )
            return {"result": False, "reason": f"Task already {release.status}"}

        # 更新状态为 processing
        release.status = "processing"
        release.save(update_fields=["status"])

    dataset = release.dataset
    version = release.version

    # 获取训练数据对象
    train_obj = train_data_model.objects.get(id=train_file_id, dataset=dataset)
    val_obj = train_data_model.objects.get(id=val_file_id, dataset=dataset)
    test_obj = train_data_model.objects.get(id=test_file_id, dataset=dataset)

    logger.info(
        f"开始发布{config.task_type}数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}"
    )

    storage = MinioBackend(bucket_name="munchkin-public")

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
                # 使用 FileField.open() 直接读取 MinIO 文件
                with file_field.open("rb") as f:
                    file_content = f.read()

                # 保存到临时目录
                local_file_path = temp_path / filename
                with open(local_file_path, "wb") as f:
                    f.write(file_content)

                # 统计样本数
                sample_count = config.count_samples(file_content)
                sample_counts[data_type] = sample_count

                logger.info(
                    f"下载文件成功: {filename}, 大小: {len(file_content)} bytes, 样本数: {sample_count}"
                )

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
            date_prefixed_path = iso_date_prefix(dataset, zip_filename)
            zip_object_path = f"{config.storage_prefix}/{dataset.id}/{date_prefixed_path}"

            saved_path = storage.save(zip_object_path, f)
            zip_url = storage.url(saved_path)

        logger.info(f"数据集上传成功: {zip_url}")

        # 更新发布记录
        with transaction.atomic():
            release.status = "published"
            release.file_size = zip_size
            release.metadata = dataset_metadata
            release.dataset_file.name = saved_path
            release.save(
                update_fields=["status", "file_size", "metadata", "dataset_file"]
            )

        logger.info(
            f"{config.task_type}数据集发布成功 - Release ID: {release.id}, 样本数: {train_samples}/{val_samples}/{test_samples}"
        )

        return {"result": True, "release_id": release_id}
