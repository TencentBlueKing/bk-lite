"""
异常检测相关的 Celery 任务
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
    异步发布异常检测数据集版本

    Args:
        release_id: AnomalyDetectionDatasetRelease 的主键
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果
    """
    release = None

    try:
        from django.db import transaction
        from apps.mlops.models.anomaly_detection import (
            AnomalyDetectionDatasetRelease,
            AnomalyDetectionTrainData,
        )

        # 使用行锁防止并发执行
        with transaction.atomic():
            release = AnomalyDetectionDatasetRelease.objects.select_for_update().get(
                id=release_id
            )

            # 防止重复执行：检查当前状态
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
        train_obj = AnomalyDetectionTrainData.objects.get(
            id=train_file_id, dataset=dataset
        )
        val_obj = AnomalyDetectionTrainData.objects.get(id=val_file_id, dataset=dataset)
        test_obj = AnomalyDetectionTrainData.objects.get(
            id=test_file_id, dataset=dataset
        )

        logger.info(
            f"开始发布数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}"
        )

        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            logger.info(f"创建临时目录: {temp_path}")

            # 初始化统计信息
            train_samples = 0
            val_samples = 0
            test_samples = 0
            train_anomaly_count = 0
            val_anomaly_count = 0
            test_anomaly_count = 0

            # 下载文件并统计样本数和异常数
            for data_obj, filename, data_type in [
                (train_obj, "train_data.csv", "train"),
                (val_obj, "val_data.csv", "val"),
                (test_obj, "test_data.csv", "test"),
            ]:
                if data_obj.train_data and data_obj.train_data.name:
                    # 使用 FileField.open() 直接读取 MinIO 文件
                    with data_obj.train_data.open("rb") as f:
                        file_content = f.read()

                    # 保存到临时目录
                    local_file = temp_path / filename
                    with open(local_file, "wb") as f:
                        f.write(file_content)

                    # 统计样本数（CSV 文件行数 - 1 表头）
                    line_count = file_content.decode("utf-8").count("\n")
                    sample_count = max(0, line_count - 1)

                    # 统计异常数（从 metadata 获取）
                    anomaly_count = 0
                    if data_obj.metadata:
                        # S3JSONField 会自动加载为 dict
                        metadata = (
                            data_obj.metadata
                            if isinstance(data_obj.metadata, dict)
                            else {}
                        )
                        anomaly_point = metadata.get("anomaly_point", [])
                        anomaly_count = (
                            len(anomaly_point) if isinstance(anomaly_point, list) else 0
                        )

                    # 分类统计
                    if data_type == "train":
                        train_samples = sample_count
                        train_anomaly_count = anomaly_count
                    elif data_type == "val":
                        val_samples = sample_count
                        val_anomaly_count = anomaly_count
                    elif data_type == "test":
                        test_samples = sample_count
                        test_anomaly_count = anomaly_count

                    logger.info(
                        f"下载文件成功: {filename}, 大小: {len(file_content)} bytes, 样本数: {sample_count}, 异常数: {anomaly_count}"
                    )

            # 生成数据集元信息
            total_samples = train_samples + val_samples + test_samples
            total_anomaly_count = (
                train_anomaly_count + val_anomaly_count + test_anomaly_count
            )

            dataset_metadata = {
                "train_samples": train_samples,
                "val_samples": val_samples,
                "test_samples": test_samples,
                "total_samples": total_samples,
                "train_anomaly_count": train_anomaly_count,
                "val_anomaly_count": val_anomaly_count,
                "test_anomaly_count": test_anomaly_count,
                "total_anomaly_count": total_anomaly_count,
                "anomaly_rate": round(total_anomaly_count / total_samples, 4)
                if total_samples > 0
                else 0,
                "features": ["timestamp", "value"],  # 根据实际数据动态提取
                "data_types": {"timestamp": "string", "value": "float"},
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
            zip_filename = f"anomaly_detection_dataset_{dataset.name}_{version}.zip"
            zip_path = temp_path / zip_filename

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in temp_path.iterdir():
                    if file_path != zip_path and file_path.suffix in [".csv", ".json"]:
                        zipf.write(file_path, file_path.name)

            zip_size = zip_path.stat().st_size
            zip_size_mb = zip_size / 1024 / 1024

            logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

            # 上传ZIP文件到MinIO
            storage = MinioBackend(bucket_name="munchkin-public")

            with open(zip_path, "rb") as f:
                date_prefixed_path = iso_date_prefix(dataset, zip_filename)
                zip_object_path = (
                    f"anomaly_detection_datasets/{dataset.id}/{date_prefixed_path}"
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
                f"数据集发布成功 - Release ID: {release_id}, Version: {version}"
            )

            return {
                "result": True,
                "release_id": release_id,
                "version": version,
                "file_size_mb": zip_size_mb,
                "metadata": dataset_metadata,
            }

    except Exception as e:
        logger.error(f"数据集发布失败: {str(e)}", exc_info=True)
        _mark_as_failed(release_id)
        return {"result": False, "release_id": release_id, "error": str(e)}


def _mark_as_failed(release_id):
    """标记发布记录为失败状态"""
    try:
        from apps.mlops.models.anomaly_detection import AnomalyDetectionDatasetRelease

        release = AnomalyDetectionDatasetRelease.objects.get(id=release_id)
        release.status = "failed"
        release.save(update_fields=["status"])
        logger.info(f"标记发布记录为失败 - Release ID: {release_id}")
    except Exception as e:
        logger.error(f"标记失败状态时出错: {str(e)}", exc_info=True)
