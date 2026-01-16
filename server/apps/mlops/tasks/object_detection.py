"""
目标检测相关的 Celery 任务
"""

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone
from django.db import transaction
from django_minio_backend import MinioBackend, iso_date_prefix

import tempfile
import zipfile
import json
import yaml
from pathlib import Path
from collections import defaultdict

from apps.core.logger import opspilot_logger as logger


@shared_task(
    soft_time_limit=7200,  # 120 分钟（图片处理较慢）
    time_limit=7260,
    acks_late=True,
    reject_on_worker_lost=True,
)
def publish_dataset_release_async(release_id, train_file_id, val_file_id, test_file_id):
    """
    异步发布目标检测数据集版本（YOLO 格式）

    Args:
        release_id: ObjectDetectionDatasetRelease 的主键
        train_file_id: 训练数据文件 ID
        val_file_id: 验证数据文件 ID
        test_file_id: 测试数据文件 ID

    Returns:
        dict: 执行结果
    """
    release = None

    try:
        from apps.mlops.models.object_detection import (
            ObjectDetectionDatasetRelease,
            ObjectDetectionTrainData,
        )

        # 获取发布记录
        release = ObjectDetectionDatasetRelease.objects.get(id=release_id)

        # 防止重复执行：检查当前状态
        if release.status in ["published", "failed"]:
            logger.info(
                f"任务已结束 - Release ID: {release_id}, 状态: {release.status}, 跳过执行"
            )
            return {"result": False, "reason": f"Task already {release.status}"}

        dataset = release.dataset
        version = release.version

        # 获取训练数据对象
        train_obj = ObjectDetectionTrainData.objects.get(
            id=train_file_id, dataset=dataset
        )
        val_obj = ObjectDetectionTrainData.objects.get(id=val_file_id, dataset=dataset)
        test_obj = ObjectDetectionTrainData.objects.get(
            id=test_file_id, dataset=dataset
        )

        logger.info(
            f"开始发布目标检测数据集 - Dataset: {dataset.id}, Version: {version}, Release ID: {release_id}"
        )

        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            logger.info(f"创建临时目录: {temp_path}")

            # 创建 YOLO 数据集结构
            yolo_root = temp_path / "dataset"
            yolo_root.mkdir()

            # 创建 images 和 labels 目录结构
            for split_name in ["train", "val", "test"]:
                (yolo_root / "images" / split_name).mkdir(parents=True)
                (yolo_root / "labels" / split_name).mkdir(parents=True)

            # 初始化统计信息
            statistics = {"total_images": 0, "classes": set(), "splits": {}}

            # 处理 train/val/test 三个数据集
            for data_obj, split_name in [
                (train_obj, "train"),
                (val_obj, "val"),
                (test_obj, "test"),
            ]:
                # 下载并解压 ZIP 文件
                if data_obj.train_data and data_obj.train_data.name:
                    logger.info(f"处理 {split_name} 数据: {data_obj.name}")

                    # 下载 ZIP
                    with data_obj.train_data.open("rb") as f:
                        zip_content = f.read()

                    # 解压到临时目录
                    temp_extract = temp_path / f"{split_name}_extract"
                    temp_extract.mkdir()
                    temp_zip = temp_path / f"{split_name}_temp.zip"
                    with open(temp_zip, "wb") as f:
                        f.write(zip_content)

                    with zipfile.ZipFile(temp_zip, "r") as zipf:
                        zipf.extractall(temp_extract)

                    # 重组为 YOLO 格式（images/split/ + labels/split/）
                    try:
                        split_stats = _reorganize_yolo_data(
                            temp_extract,
                            yolo_root / "images" / split_name,
                            yolo_root / "labels" / split_name,
                            data_obj.metadata,
                        )
                    except ValueError as e:
                        error_msg = f"{split_name} 数据处理失败: {e}"
                        logger.error(error_msg)
                        raise ValueError(error_msg) from e
                    except Exception as e:
                        error_msg = f"{split_name} 数据处理时发生未预期的错误: {e}"
                        logger.error(error_msg, exc_info=True)
                        raise ValueError(error_msg) from e

                    # 转换 split_stats 中的 set 为 list，以便后续 JSON 序列化
                    split_stats_serializable = {
                        "total": split_stats["total"],
                        "classes": sorted(list(split_stats["classes"])),
                    }
                    statistics["splits"][split_name] = split_stats_serializable
                    statistics["total_images"] += split_stats["total"]
                    statistics["classes"].update(split_stats["classes"])

                    logger.info(
                        f"{split_name} 处理完成: {split_stats['total']} 张图片, {len(split_stats['classes'])} 个类别"
                    )

            # 转换 set 为 sorted list
            classes_list = sorted(list(statistics["classes"]))
            statistics["classes"] = classes_list

            # 生成 data.yaml
            data_yaml_content = {
                "path": ".",
                "train": "images/train",
                "val": "images/val",
                "test": "images/test",
                "names": {
                    idx: class_name for idx, class_name in enumerate(classes_list)
                },
            }

            with open(yolo_root / "data.yaml", "w", encoding="utf-8") as f:
                yaml.dump(
                    data_yaml_content, f, allow_unicode=True, default_flow_style=False
                )

            # 生成完整的 metadata
            dataset_metadata = {
                "total_images": statistics["total_images"],
                "classes": classes_list,
                "num_classes": len(classes_list),
                "format": "YOLO",
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
            metadata_file = yolo_root / "dataset_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(dataset_metadata, f, ensure_ascii=False, indent=2)

            # 创建 ZIP 压缩包
            zip_filename = f"object_detection_dataset_{dataset.name}_{version}.zip"
            zip_path = temp_path / zip_filename

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in yolo_root.walk():
                    for file in files:
                        file_path = root / file
                        arcname = file_path.relative_to(yolo_root)
                        zipf.write(file_path, arcname)

            zip_size = zip_path.stat().st_size
            zip_size_mb = zip_size / 1024 / 1024

            logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

            # 上传 ZIP 文件到 MinIO
            storage = MinioBackend(bucket_name="munchkin-public")

            with open(zip_path, "rb") as f:
                date_prefixed_path = iso_date_prefix(dataset, zip_filename)
                zip_object_path = (
                    f"object_detection_datasets/{dataset.id}/{date_prefixed_path}"
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
                f"目标检测数据集发布成功 - Release ID: {release_id}, Version: {version}"
            )

            return {
                "result": True,
                "release_id": release_id,
                "version": version,
                "file_size_mb": zip_size_mb,
                "metadata": dataset_metadata,
            }

    except SoftTimeLimitExceeded:
        logger.error(f"任务超时 - Release ID: {release_id}")
        _mark_as_failed(release_id, "任务超时")
        return {"result": False, "reason": "Task timeout"}

    except Exception as e:
        logger.error(f"数据集发布失败: {str(e)}", exc_info=True)
        _mark_as_failed(release_id, str(e))
        return {"result": False, "error": str(e)}


def _reorganize_yolo_data(
    extract_dir: Path, images_dir: Path, labels_dir: Path, metadata: dict
) -> dict:
    """
    将原始数据重组为 YOLO 格式

    Args:
        extract_dir: 解压后的临时目录
        images_dir: 目标图片目录（images/split/）
        labels_dir: 目标标注目录（labels/split/）
        metadata: TrainData 的 metadata，格式：
            {
                "labels": {
                    "img1.jpg": [
                        {"class_id": 0, "x_center": 0.5, "y_center": 0.5, "width": 0.3, "height": 0.4},
                        ...
                    ]
                },
                "classes": ["cat", "dog", "person"],
                "statistics": {"total_images": 100, "total_annotations": 250}
            }

    Returns:
        dict: 统计信息 {total, classes: set()}

    Raises:
        ValueError: 当 metadata 格式不正确时
    """
    import shutil

    classes_found = set()
    total = 0

    # 验证 metadata
    if not metadata:
        error_msg = "metadata 为空，无法重组 YOLO 数据"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not isinstance(metadata, dict):
        error_msg = f"metadata 必须是字典类型，实际类型: {type(metadata).__name__}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 获取标签映射和类别列表
    labels_map = metadata.get("labels")
    classes = metadata.get("classes")

    if labels_map is None:
        error_msg = "metadata 中缺少必需字段 'labels'"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not isinstance(labels_map, dict):
        error_msg = (
            f"metadata.labels 必须是字典类型，实际类型: {type(labels_map).__name__}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    if classes is None:
        error_msg = "metadata 中缺少必需字段 'classes'"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not isinstance(classes, list):
        error_msg = (
            f"metadata.classes 必须是列表类型，实际类型: {type(classes).__name__}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not labels_map:
        logger.warning("metadata.labels 为空字典，没有标注数据")

    if not classes:
        logger.warning("metadata.classes 为空列表，没有类别信息")

    # 遍历所有图片文件
    image_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]
    images_found = []

    for img_file in extract_dir.rglob("*"):
        if img_file.is_file() and img_file.suffix.lower() in image_extensions:
            images_found.append(img_file)

    if not images_found:
        error_msg = f"在解压目录 {extract_dir} 中未找到任何图片文件（支持格式: {', '.join(image_extensions)}）"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(f"在解压目录中找到 {len(images_found)} 张图片")

    # 处理每张图片
    processed_count = 0
    skipped_count = 0
    annotation_count = 0

    for img_file in images_found:
        try:
            img_name = img_file.name

            # 复制图片到 images_dir
            target_img = images_dir / img_name
            shutil.copy2(img_file, target_img)
            processed_count += 1

            # 如果有标注信息，生成 YOLO 格式的 txt 文件
            if img_name in labels_map:
                annotations = labels_map[img_name]

                if not isinstance(annotations, list):
                    logger.warning(
                        f"图片 '{img_name}' 的标注不是列表类型（{type(annotations).__name__}），跳过"
                    )
                    label_file = labels_dir / f"{img_file.stem}.txt"
                    label_file.touch()
                    continue

                label_file = labels_dir / f"{img_file.stem}.txt"

                with open(label_file, "w", encoding="utf-8") as f:
                    valid_annotations = 0
                    for idx, ann in enumerate(annotations):
                        try:
                            if not isinstance(ann, dict):
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注不是字典类型，跳过"
                                )
                                continue

                            # 提取标注字段
                            class_id = ann.get("class_id")
                            x_center = ann.get("x_center")
                            y_center = ann.get("y_center")
                            width = ann.get("width")
                            height = ann.get("height")

                            # 验证必需字段
                            if class_id is None:
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注缺少 class_id，跳过"
                                )
                                continue

                            if any(
                                v is None for v in [x_center, y_center, width, height]
                            ):
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注缺少坐标字段，跳过"
                                )
                                continue

                            # 验证 class_id 范围
                            if not isinstance(class_id, int) or class_id < 0:
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_id ({class_id}) 无效，跳过"
                                )
                                continue

                            if class_id >= len(classes):
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注: class_id ({class_id}) 超出范围 [0, {len(classes) - 1}]，跳过"
                                )
                                continue

                            # 验证坐标范围（YOLO 格式要求 0-1）
                            coords = {
                                "x_center": x_center,
                                "y_center": y_center,
                                "width": width,
                                "height": height,
                            }
                            invalid_coords = [
                                k
                                for k, v in coords.items()
                                if not isinstance(v, (int, float)) or v < 0 or v > 1
                            ]
                            if invalid_coords:
                                logger.warning(
                                    f"图片 '{img_name}' 的第 {idx + 1} 个标注: 坐标值 {invalid_coords} 超出范围 [0, 1]，跳过"
                                )
                                continue

                            # YOLO 格式：class_id x_center y_center width height
                            f.write(
                                f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n"
                            )
                            valid_annotations += 1
                            annotation_count += 1

                            # 记录类别
                            if class_id < len(classes):
                                classes_found.add(classes[class_id])

                        except Exception as e:
                            logger.error(
                                f"处理图片 '{img_name}' 的第 {idx + 1} 个标注时出错: {e}",
                                exc_info=True,
                            )
                            continue

                logger.debug(
                    f"生成标注: {label_file.name} ({valid_annotations}/{len(annotations)} 个有效目标)"
                )
            else:
                # 无标注时生成空文件（符合 YOLO 规范）
                label_file = labels_dir / f"{img_file.stem}.txt"
                label_file.touch()
                logger.debug(f"生成空标注: {label_file.name}")

            total += 1

        except Exception as e:
            logger.error(f"处理图片 '{img_file.name}' 时出错: {e}", exc_info=True)
            skipped_count += 1
            continue

    logger.info(
        f"数据重组完成: 成功处理 {processed_count} 张图片, 跳过 {skipped_count} 张, "
        f"生成 {annotation_count} 个标注框, 发现 {len(classes_found)} 个类别"
    )

    if total == 0:
        error_msg = "没有成功处理任何图片"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return {"total": total, "classes": classes_found}


def _mark_as_failed(release_id, error_message="Unknown error"):
    """标记发布任务为失败状态"""
    try:
        from apps.mlops.models.object_detection import ObjectDetectionDatasetRelease

        release = ObjectDetectionDatasetRelease.objects.get(id=release_id)
        release.status = "failed"
        release.metadata = {
            "error": error_message,
            "failed_at": timezone.now().isoformat(),
        }
        release.save(update_fields=["status", "metadata"])

        logger.error(
            f"标记发布任务为失败 - Release ID: {release_id}, 原因: {error_message}"
        )
    except Exception as e:
        logger.error(f"更新失败状态失败: {str(e)}", exc_info=True)
