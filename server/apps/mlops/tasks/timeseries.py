"""
时间序列预测相关的 Celery 任务
"""

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone
from django.db import transaction
from django_minio_backend import MinioBackend, iso_date_prefix

import tempfile
import zipfile
import json
import time
from pathlib import Path

from apps.core.logger import mlops_logger as logger


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
        release_id: TimeSeriesPredictDatasetRelease 的主键
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果
    """
    release = None

    try:
        from django.db import transaction
        from apps.mlops.models.timeseries_predict import (
            TimeSeriesPredictDatasetRelease,
            TimeSeriesPredictTrainData,
        )

        # 使用行锁防止并发执行
        with transaction.atomic():
            release = TimeSeriesPredictDatasetRelease.objects.select_for_update().get(
                id=release_id
            )

            # 防止重复执行:检查当前状态
            if release.status in ["published", "failed"]:
                logger.info(
                    f"任务已结束 - Release ID: {release_id}, 状态: {release.status}, 跳过执行"
                )
                return {"result": False, "reason": f"Task already {release.status}"}

            # 更新状态为processing
            release.status = "processing"
            release.save(update_fields=["status"])

        dataset = release.dataset
        version = release.version

        # 获取训练数据对象
        train_obj = TimeSeriesPredictTrainData.objects.get(
            id=train_file_id, dataset=dataset
        )
        val_obj = TimeSeriesPredictTrainData.objects.get(
            id=val_file_id, dataset=dataset
        )
        test_obj = TimeSeriesPredictTrainData.objects.get(
            id=test_file_id, dataset=dataset
        )

        logger.info(
            f"开始发布数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}"
        )

        storage = MinioBackend(bucket_name="munchkin-public")

        # 创建临时目录用于存放文件
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # 通过 ORM FileField 直接读取 MinIO 文件
            files_info = [
                (train_obj.train_data, "train_data.csv"),
                (val_obj.train_data, "val_data.csv"),
                (test_obj.train_data, "test_data.csv"),
            ]

            # 统计数据集信息
            train_samples = 0
            val_samples = 0
            test_samples = 0

            for file_field, filename in files_info:
                if file_field and file_field.name:
                    # 使用 FileField.open() 直接读取 MinIO 文件
                    with file_field.open("rb") as f:
                        file_content = f.read()

                    # 保存到临时目录
                    local_file_path = temp_path / filename
                    with open(local_file_path, "wb") as f:
                        f.write(file_content)

                    # 统计样本数（CSV文件行数-1表头）
                    line_count = file_content.decode("utf-8").count("\n")
                    sample_count = max(0, line_count - 1)

                    if "train" in filename:
                        train_samples = sample_count
                    elif "val" in filename:
                        val_samples = sample_count
                    elif "test" in filename:
                        test_samples = sample_count

                    logger.info(
                        f"下载文件成功: {filename}, 大小: {len(file_content)} bytes, 样本数: {sample_count}"
                    )

            # 生成数据集元信息
            total_samples = train_samples + val_samples + test_samples
            dataset_metadata = {
                "train_samples": train_samples,
                "val_samples": val_samples,
                "test_samples": test_samples,
                "total_samples": total_samples,
                "features": ["timestamp", "value"],
                "data_types": {"timestamp": "datetime", "value": "float"},
                # "split_ratio": {
                #     "train": round(train_samples / total_samples, 3) if total_samples > 0 else 0,
                #     "val": round(val_samples / total_samples, 3) if total_samples > 0 else 0,
                #     "test": round(test_samples / total_samples, 3) if total_samples > 0 else 0
                # },
                "source": {
                    "type": "manual_selection",
                    "train_file_id": train_file_id,
                    "val_file_id": val_file_id,
                    "test_file_id": test_file_id,
                    "train_file_name": train_obj.name,
                    "val_file_name": val_obj.name,
                    "test_file_name": test_obj.name,
                },
            }

            # 保存数据集元信息到临时文件
            metadata_file = temp_path / "dataset_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(dataset_metadata, f, ensure_ascii=False, indent=2)

            # 创建ZIP压缩包
            zip_filename = f"timeseries_dataset_{dataset.name}_{version}.zip"
            zip_path = temp_path / zip_filename

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_path.iterdir():
                    if file_path != zip_path:
                        zipf.write(file_path, file_path.name)

            zip_size = zip_path.stat().st_size
            zip_size_mb = zip_size / 1024 / 1024
            logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

            # 上传ZIP文件到MinIO
            with open(zip_path, "rb") as f:
                date_prefixed_path = iso_date_prefix(dataset, zip_filename)
                zip_object_path = (
                    f"timeseries_datasets/{dataset.id}/{date_prefixed_path}"
                )

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
                f"数据集发布成功 - Release ID: {release.id}, 样本数: {train_samples}/{val_samples}/{test_samples}"
            )

            return {"result": True, "release_id": release_id}

    except SoftTimeLimitExceeded:
        logger.error(f"数据集发布超时 - Release ID: {release_id}")
        _mark_as_failed(release_id)
        raise

    except Exception as exc:
        logger.error(f"数据集发布失败 - Release ID: {release_id}", exc_info=True)
        _mark_as_failed(release_id)
        raise


def _mark_as_failed(release_id):
    """标记发布记录为失败状态"""
    try:
        from apps.mlops.models.timeseries_predict import TimeSeriesPredictDatasetRelease

        release = TimeSeriesPredictDatasetRelease.objects.get(id=release_id)
        release.status = "failed"
        release.save(update_fields=["status"])
    except Exception as e:
        logger.error(f"更新失败状态失败 - Release ID: {release_id} - {str(e)}")
