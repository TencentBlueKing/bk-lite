"""
图片分类相关的 Celery 任务
"""

import json
import shutil
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django_minio_backend import MinioBackend, iso_date_prefix

from apps.core.logger import mlops_logger as logger
from apps.mlops.tasks.base import (
    DatasetReleaseAttempt,
    DatasetReleaseBusy,
    build_publish_object_name,
    claim_dataset_release,
    finalize_uploaded_dataset_release,
    get_storage_display_url,
    mark_release_as_failed,
    prepare_claim_storage,
    save_dataset_release_object,
)

ZIP_COPY_CHUNK_SIZE = 64 * 1024


@shared_task(
    bind=True,
    max_retries=None,
    soft_time_limit=7200,  # 120 分钟（图片处理较慢）
    time_limit=7260,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_dataset_release_async(self, release_id, train_file_id, val_file_id, test_file_id):
    """
    异步发布图片分类数据集版本

    Args:
        release_id: ImageClassificationDatasetRelease 的主键
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果
    """
    release = None
    attempt = DatasetReleaseAttempt()

    try:
        from apps.mlops.models.image_classification import ImageClassificationDatasetRelease, ImageClassificationTrainData

        claim = claim_dataset_release(
            ImageClassificationDatasetRelease,
            release_id,
            attempt=attempt,
        )
        storage = prepare_claim_storage(claim)
        if not claim.acquired:
            return {"result": False, "reason": claim.reason}
        release = claim.release
        execution_token = claim.owner_token
        cleanup_owner_token = execution_token or attempt.candidate_token
        if storage is None:
            storage = MinioBackend(
                bucket_name="munchkin-public",
                replace_existing=execution_token is not None,
            )

        dataset = release.dataset
        version = release.version

        # 获取训练数据对象
        train_obj = ImageClassificationTrainData.objects.get(id=train_file_id, dataset=dataset)
        val_obj = ImageClassificationTrainData.objects.get(id=val_file_id, dataset=dataset)
        test_obj = ImageClassificationTrainData.objects.get(id=test_file_id, dataset=dataset)

        logger.info(f"开始发布图片分类数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}")

        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            logger.info(f"创建临时目录: {temp_path}")

            # 创建 ImageFolder 结构
            imagefolder_root = temp_path / "dataset"
            imagefolder_root.mkdir()

            # 初始化统计信息
            statistics = {"total_images": 0, "classes": set(), "splits": {}}

            # 处理 train/val/test 三个数据集
            for data_obj, split_name in [
                (train_obj, "train"),
                (val_obj, "val"),
                (test_obj, "test"),
            ]:
                split_root = imagefolder_root / split_name
                split_root.mkdir()

                # 下载并解压 ZIP 文件
                if data_obj.train_data and data_obj.train_data.name:
                    logger.info(f"处理 {split_name} 数据: {data_obj.name}")

                    # 解压到临时目录（扁平化）
                    temp_extract = temp_path / f"{split_name}_extract"
                    temp_extract.mkdir()
                    temp_zip = temp_path / f"{split_name}_temp.zip"
                    with data_obj.train_data.open("rb") as source, open(temp_zip, "wb") as target:
                        shutil.copyfileobj(source, target, length=ZIP_COPY_CHUNK_SIZE)

                    with zipfile.ZipFile(temp_zip, "r") as zipf:
                        zipf.extractall(temp_extract)

                    # 根据 metadata 重组为 ImageFolder 格式
                    split_stats = _reorganize_images(temp_extract, split_root, data_obj.metadata)
                    statistics["splits"][split_name] = split_stats
                    statistics["total_images"] += split_stats["total"]
                    statistics["classes"].update(split_stats["classes"].keys())

                    logger.info(f"{split_name} 处理完成: {split_stats['total']} 张图片, {len(split_stats['classes'])} 个类别")

            # 转换 set 为 sorted list
            statistics["classes"] = sorted(list(statistics["classes"]))

            # 生成完整的 metadata
            dataset_metadata = {
                "total_images": statistics["total_images"],
                "classes": statistics["classes"],
                "num_classes": len(statistics["classes"]),
                "format": "ImageFolder",
                "splits": statistics["splits"],
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

            # 保存 metadata.json
            metadata_file = imagefolder_root / "dataset_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(dataset_metadata, f, ensure_ascii=False, indent=2)

            # 创建 ZIP 压缩包
            zip_filename = f"image_classification_dataset_{dataset.name}_{version}.zip"
            zip_path = temp_path / zip_filename

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in imagefolder_root.walk():
                    for file in files:
                        file_path = root / file
                        arcname = file_path.relative_to(imagefolder_root)
                        zipf.write(file_path, arcname)

            zip_size = zip_path.stat().st_size
            zip_size_mb = zip_size / 1024 / 1024

            logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

            # 上传 ZIP 文件到 MinIO
            with open(zip_path, "rb") as f:
                object_name = build_publish_object_name(zip_filename, execution_token)
                date_prefixed_path = iso_date_prefix(dataset, object_name)
                zip_object_path = f"image_classification_datasets/{dataset.id}/{date_prefixed_path}"

                saved_path = save_dataset_release_object(
                    storage,
                    f,
                    zip_object_path,
                    ImageClassificationDatasetRelease,
                    release_id,
                    execution_token,
                    cleanup_owner_token,
                )
                if saved_path is None:
                    logger.warning(
                        "图片分类发布上传前 owner 已失效 - Release ID: %s",
                        release_id,
                    )
                    return {"result": False, "reason": "Stale execution"}

            finalized = finalize_uploaded_dataset_release(
                storage,
                saved_path,
                ImageClassificationDatasetRelease,
                release_id,
                execution_token,
                file_size=zip_size,
                metadata=dataset_metadata,
                cleanup_owner_token=cleanup_owner_token,
            )
            if not finalized:
                logger.warning("陈旧图片分类发布结果已丢弃 - Release ID: %s", release_id)
                return {"result": False, "reason": "Stale execution"}

            zip_url = get_storage_display_url(storage, saved_path)
            logger.info(f"数据集上传成功: {zip_url}")

            logger.info(f"图片分类数据集发布成功 - Release ID: {release_id}, Version: {version}")

            return {
                "result": True,
                "release_id": release_id,
                "version": version,
                "file_size_mb": zip_size_mb,
                "metadata": dataset_metadata,
            }

    except DatasetReleaseBusy as exc:
        raise self.retry(exc=exc, countdown=exc.retry_after, max_retries=None)

    except SoftTimeLimitExceeded:
        logger.error(f"任务超时 - Release ID: {release_id}")
        if attempt.can_mark_failure():
            from apps.mlops.models.image_classification import ImageClassificationDatasetRelease

            mark_release_as_failed(
                ImageClassificationDatasetRelease,
                release_id,
                "任务超时",
                owner_token=attempt.owner_token,
                cleanup_owner_token=attempt.candidate_token,
            )
        return {"result": False, "reason": "Task timeout"}

    except Exception as e:
        logger.error(f"数据集发布失败: {str(e)}", exc_info=True)
        if attempt.can_mark_failure():
            from apps.mlops.models.image_classification import ImageClassificationDatasetRelease

            mark_release_as_failed(
                ImageClassificationDatasetRelease,
                release_id,
                str(e),
                owner_token=attempt.owner_token,
                cleanup_owner_token=attempt.candidate_token,
            )
        return {"result": False, "error": str(e)}


def _reorganize_images(extract_dir: Path, split_root: Path, metadata: dict) -> dict:
    """
    将扁平化的图片根据 metadata 重组为 ImageFolder 格式

    Args:
        extract_dir: 解压后的临时目录（扁平化的图片）
        split_root: 目标目录（ImageFolder 格式）
        metadata: TrainData 的 metadata，格式：
            {
                "labels": {"img1.jpg": "cat", "img2.jpg": "dog"},
                "classes": ["cat", "dog"],
                "statistics": {"class_distribution": {"cat": 10, "dog": 5}}
            }

    Returns:
        dict: 统计信息 {total, classes: {class_name: count}}
    """
    import shutil

    class_counts = defaultdict(int)
    total = 0

    if not metadata:
        logger.warning("metadata 为空，无法重组图片")
        return {"total": 0, "classes": {}}

    # 获取标签映射和类别列表
    labels = metadata.get("labels", {})
    classes = metadata.get("classes", [])

    if not labels:
        logger.warning("metadata 中没有 labels 字段，无法重组图片")
        return {"total": 0, "classes": {}}

    # 创建所有类别文件夹
    for class_name in classes:
        class_dir = split_root / class_name
        class_dir.mkdir(exist_ok=True)

    # 遍历所有图片文件，根据 labels 移动到对应类别文件夹
    for img_file in extract_dir.rglob("*"):
        if img_file.is_file() and img_file.suffix.lower() in [
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".gif",
            ".webp",
        ]:
            img_name = img_file.name

            # 从 labels 中查找该图片的类别
            if img_name in labels:
                class_name = labels[img_name]
                target_dir = split_root / class_name

                # 安全检查：防止目录遍历攻击
                try:
                    target_dir.resolve().relative_to(split_root.resolve())
                except ValueError:
                    logger.error(f"检测到非法路径: {class_name}")
                    continue

                target_dir.mkdir(exist_ok=True)

                # 移动文件
                target_file = target_dir / img_name
                shutil.copy2(img_file, target_file)

                class_counts[class_name] += 1
                total += 1

                logger.debug(f"移动图片: {img_name} -> {class_name}/")
            else:
                logger.warning(f"图片 {img_name} 在 metadata.labels 中未找到对应类别，跳过")

    return {"total": total, "classes": dict(class_counts)}
