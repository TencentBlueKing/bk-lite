from re import S
import scipy as sp
from config.drf.viewsets import ModelViewSet
from config.drf.pagination import CustomPageNumberPagination

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.object_detection import *
from apps.mlops.filters.object_detection import *
from apps.mlops.serializers.object_detection import *
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django_minio_backend import MinioBackend,iso_date_prefix

from PIL import Image
from io import BytesIO
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime


class ObjectDetectionDatasetViewSet(ModelViewSet):
  queryset = ObjectDetectionDataset.objects.all()
  serializer_class = ObjectDetectionDatasetSerializers
  filterset_class = ObjectDetectionDatasetFilter
  pagination_class = CustomPageNumberPagination
  ordering = "-id"
  permission_key = "dataset.object_detection_dataset"
  
  @HasPermission("object_detection_datasets-View")
  def list(self, request, *args, **kwargs):
      return super().list(request, *args, **kwargs)

  @HasPermission("object_detection_datasets-View")
  def retrieve(self, request, *args, **kwargs):
      return super().retrieve(request, *args, **kwargs)

  @HasPermission("object_detection_datasets-Delete")
  def destroy(self, request, *args, **kwargs):
      return super().destroy(request, *args, **kwargs)

  @HasPermission("object_detection_datasets-Add")
  def create(self, request, *args, **kwargs):
      return super().create(request, *args, **kwargs)

  @HasPermission("object_detection_datasets-Edit")
  def update(self, request, *args, **kwargs):
      return super().update(request, *args, **kwargs)
  
class ObjectDetectionTrainDataViewSet(ModelViewSet):
    queryset = ObjectDetectionTrainData.objects.all()
    serializer_class = ObjectDetectionTrainDataSerializers
    pagination_class = CustomPageNumberPagination
    filterset_class = ObjectDetectionTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.object_detection_train_data"

    @HasPermission("object_detection_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("object_detection_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("object_detection_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        """
        删除训练数据实例,同时删除 MinIO 中的关联文件
        """
        try:
            instance = self.get_object()
            
            # 提取 train_data 中的所有图片 URL
            train_data = instance.train_data or []
            image_urls = [item.get('image_url') for item in train_data if item.get('image_url')]
            
            if not image_urls:
                logger.warning(f"实例 {instance.id} 无关联图片,仅删除数据库记录")
                return super().destroy(request, *args, **kwargs)
            
            logger.info(f"开始删除实例 {instance.id} 及其 {len(image_urls)} 个关联文件")
            
            # 获取 MinIO 存储后端
            # bucket_name = getattr(settings, 'MINIO_PUBLIC_BUCKETS', )
            storage = MinioBackend(bucket_name='munchkin-public')
            
            # 删除 MinIO 中的文件
            deleted_count = 0
            failed_files = []
            
            for idx, image_url in enumerate(image_urls, 1):
                try:
                    object_name = self._extract_object_name(image_url, 'munchkin-public')
                    
                    if storage.exists(object_name):
                        storage.delete(object_name)
                        deleted_count += 1
                        logger.info(f"删除文件 [{idx}/{len(image_urls)}]: {object_name}")
                    else:
                        logger.warning(f"文件不存在,跳过: {object_name}")
                        
                except Exception as e:
                    failed_files.append({'url': image_url, 'error': str(e)})
                    logger.error(f"删除文件失败: {image_url}, 错误: {str(e)}")
            
            # 删除数据库记录
            instance_id = instance.id
            instance_name = instance.name
            super().destroy(request, *args, **kwargs)
            
            logger.info(
                f"实例删除完成 - ID: {instance_id}, 名称: {instance_name}, "
                f"文件删除: {deleted_count}/{len(image_urls)}, "
                f"失败: {len(failed_files)}"
            )
            
            if failed_files:
                return Response(
                    {
                        'message': '实例已删除,但部分文件删除失败,请手动删除',
                        'deleted_files': deleted_count,
                        'failed_files': failed_files
                    },
                    status=status.HTTP_200_OK
                )
            
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except Exception as e:
            logger.error(f"删除实例失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'删除失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _extract_object_name(self, image_url, bucket_name):
        """
        从完整 URL 中提取 MinIO 对象名称
        
        Args:
            image_url: 完整图片 URL,如 http://minio:9000/image-classification/2025/01/29/cat.jpg
            bucket_name: bucket 名称,如 image-classification
            
        Returns:
            对象名称,如 2025/01/29/cat.jpg
        """
        try:
            if f'/{bucket_name}/' in image_url:
                object_name = image_url.split(f'/{bucket_name}/', 1)[1]
            else:
                object_name = image_url.split('/')[-1]
                logger.warning(f"URL 格式异常,仅提取文件名: {object_name}")
            
            return object_name
        except Exception as e:
            logger.error(f"提取对象名称失败: {image_url}, 错误: {str(e)}")
            raise

    @HasPermission("object_detection_train_data-Add")
    def create(self, request, *args, **kwargs):
        """
        创建训练数据:统一使用 'images' 字段
        - 所有图片都手动上传到 MinIO,信息存储在 train_data 列表中
        - 单图/多图逻辑统一,无需区分处理
        """
        try:
            file_list = request.FILES.getlist('images', [])
            
            if not file_list:
                return Response(
                    {'error': '未检测到上传文件,请使用 images 字段上传'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 基础数据校验
            dataset_id = request.data.get('dataset')
            if not dataset_id:
                return Response(
                    {'error': '缺少必填字段: dataset'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建实例名称
            instance_name = request.data.get('name')
            if not instance_name:
                first_file_name = file_list[0].name.rsplit('.', 1)[0] if '.' in file_list[0].name else file_list[0].name
                instance_name = f"{first_file_name}_batch_{len(file_list)}" if len(file_list) > 1 else first_file_name
            
            logger.info(f"开始上传 {len(file_list)} 个图片,实例名称: {instance_name}")
            
            # 获取 MinIO 存储后端
            # bucket_name = getattr(settings, 'MINIO_PUBLIC_BUCKETS', 'munchkin-public')
            storage = MinioBackend(bucket_name='munchkin-public')
            
            # 准备 train_data 列表
            train_data_list = []
            
            # 事务保证原子性
            with transaction.atomic():
                # 先创建空实例(仅基础数据)
                instance_data = {
                    'dataset': dataset_id,
                    'name': instance_name,
                    'is_train_data': request.data.get('is_train_data', False),
                    'is_val_data': request.data.get('is_val_data', False),
                    'is_test_data': request.data.get('is_test_data', False),
                    'train_data': [],
                    'meta_data': request.data.get('meta_data', {
                        'image_label': [],
                        'yolo_dataset_url': '',
                        'class_name': []
                    })
                }
                
                serializer = self.get_serializer(data=instance_data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save()
                
                # 逐个上传图片到 MinIO
                for idx, file in enumerate(file_list, 1):
                    width, height = None, None
                    try:
                        image_data = file.read()
                        image = Image.open(BytesIO(image_data))
                        width, height = image.size
                        file.seek(0)
                    except Exception as e:
                        logger.warning(f"图片解析失败：{file.name}, 错误：{str(e)}")
                    
                    # 生成文件路径
                    file_path = iso_date_prefix(instance, file.name)
                    
                    # 上传到 MinIO
                    saved_path = storage.save(file_path, file)
                    file_url = storage.url(saved_path)
                    
                    # 记录图片信息
                    image_info = {
                        'image_name': file.name,
                        'image_size': file.size,
                        'content_type': getattr(file, 'content_type', 'unknown'),
                        'image_url': file_url,
                        'width': width,
                        'height': height,
                        'batch_index': idx,
                        'batch_total': len(file_list),
                        'type': ''
                    }
                    train_data_list.append(image_info)
                    
                    logger.info(f"图片上传成功 [{idx}/{len(file_list)}]: {file.name}, URL: {file_url}")
                
                # 更新实例的 train_data
                instance.train_data = train_data_list
                instance.save(update_fields=['train_data'])
                
                logger.info(f"批量上传完成: 共 {len(file_list)} 个文件,实例 ID: {instance.id}")
            
            # 返回创建结果
            result_serializer = self.get_serializer(instance)
            return Response(
                result_serializer.data,
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"图片上传失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'图片上传失败: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @HasPermission("object_detection_train_data-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新训练数据
        - 如果传递了 images 字段且有文件,则上传到 MinIO 并追加到 train_data
        - 否则走默认更新流程
        """
        try:
            file_list = request.FILES.getlist('images', [])
            
            # 无文件上传,走默认更新流程
            if not file_list:
                logger.info(f"更新实例 {kwargs.get('pk')}: 无新图片上传,走默认更新流程")
                return super().update(request, *args, **kwargs)
            
            # 有文件上传,执行图片上传逻辑
            instance = self.get_object()
            logger.info(f"更新实例 {instance.id}: 新增 {len(file_list)} 个图片")
            
            # 获取 MinIO 存储后端
            # bucket_name = getattr(settings, 'MINIO_PUBLIC_BUCKETS', 'munchkin-public')
            storage = MinioBackend(bucket_name='munchkin-public')
            
            # 获取现有 train_data
            existing_train_data = instance.train_data or []
            existing_count = len(existing_train_data)
            
            # 准备新增图片列表
            new_images = []
            
            # 事务保证原子性
            with transaction.atomic():
                # 逐个上传新图片到 MinIO
                for idx, file in enumerate(file_list, 1):
                    width, height = None, None
                    try:
                        image_data = file.read()
                        image = Image.open(BytesIO(image_data))
                        width, height = image.size
                        file.seek(0)
                    except Exception as e:
                        logger.warning(f"图片解析失败：{file.name}, 错误：{str(e)}")

                    file_path = iso_date_prefix(instance, file.name)
                    saved_path = storage.save(file_path, file)
                    file_url = storage.url(saved_path)
                    
                    image_info = {
                        'image_name': file.name,
                        'image_size': file.size,
                        'content_type': getattr(file, 'content_type', 'unknown'),
                        'image_url': file_url,
                        'width': width,
                        'height': height,
                        'batch_index': existing_count + idx,
                        'batch_total': existing_count + len(file_list)
                    }
                    new_images.append(image_info)
                    
                    logger.info(f"新增图片上传成功 [{idx}/{len(file_list)}]: {file.name}, URL: {file_url}")
                
                # 合并到 train_data
                instance.train_data = existing_train_data + new_images
                
                # 更新其他字段(如果有)
                update_fields = ['train_data']
                
                # 处理 meta_data: 序列化器已经自动反序列化了
                if 'meta_data' in request.data:
                    instance.meta_data = request.data.get('meta_data')
                    update_fields.append('meta_data')
                    logger.debug(f"meta_data 已更新: {instance.meta_data}")
                
                # 处理其他简单字段
                for field in ['name', 'is_train_data', 'is_val_data', 'is_test_data']:
                    if field in request.data:
                        setattr(instance, field, request.data[field])
                        update_fields.append(field)
                
                instance.save(update_fields=update_fields)
                
                logger.info(
                    f"实例更新完成 - ID: {instance.id}, "
                    f"原有图片: {existing_count}, "
                    f"新增图片: {len(file_list)}, "
                    f"总计: {len(instance.train_data)}"
                )
            
            # 返回更新结果
            result_serializer = self.get_serializer(instance)
            return Response(
                result_serializer.data,
                status=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(f"更新实例失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'更新失败: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='generate_dataset')
    @HasPermission("object_detection_train_data-Edit")
    def generate_yolo_dataset(self, request, *args, **kwargs):
        """
        生成 YOLO 格式数据集并上传到 MinIO
        
        数据结构:
        - train_data: 包含图片信息和类型标记 (type: train/val/test)
        - meta_data.image_label: 包含标注信息 (通过 image_url 关联)
        - meta_data.class_name: 类别名称列表
        
        数据集结构:
        - images/train/: 训练集图片
        - images/val/: 验证集图片
        - images/test/: 测试集图片（可选）
        - labels/train/: 训练集标注
        - labels/val/: 验证集标注
        - labels/test/: 测试集标注（可选）
        - data.yaml: 数据集配置
        """
        try:
            instance = self.get_object()

            train_data = instance.train_data or []
            meta_data = instance.meta_data or {}

            if not train_data:
                return Response(
                    {'error': '训练数据为空, 无法生成数据集'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            image_labels = meta_data.get('image_label', [])
            class_names = meta_data.get('class_name', [])

            if not image_labels:
                return Response(
                    {'error': 'meta_data 中缺少 image_label 标注信息'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not class_names:
                return Response(
                    {'error': 'meta_data 中缺少 class_name 类别信息'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 检查必须类型（从 train_data 中获取）
            image_types = {item.get('type') for item in train_data if item.get('type')}

            if 'train' not in image_types:
                return Response(
                    {'error': 'train_data 中缺少 train 类型的图片'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if 'val' not in image_types:
                return Response(
                    {'error': 'train_data 中缺少 val 类型的图片'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            logger.info(
                f"开始生成 YOLO 数据集 - 实例: {instance.id}, "
                f"图片数: {len(train_data)}, 类别数: {len(class_names)}, "
                f"类型分布: {image_types}"
            )

            # 创建临时目录结构
            with tempfile.TemporaryDirectory() as temp_dir:
                dataset_root = Path(temp_dir) / f'object_detection_{instance.id}'
                
                # 创建分类子目录（仅创建实际存在的类型）
                dir_structure = {}
                for split_type in ['train', 'val', 'test']:
                    if split_type in image_types:
                        images_dir = dataset_root / 'images' / split_type
                        labels_dir = dataset_root / 'labels' / split_type

                        images_dir.mkdir(parents=True, exist_ok=True)
                        labels_dir.mkdir(parents=True, exist_ok=True)

                        dir_structure[split_type] = {
                            'images': images_dir,
                            'labels': labels_dir
                        }

                # 获取存储后端
                storage = MinioBackend(bucket_name='munchkin-public')

                # 构建 URL 到标注的映射
                label_map = {label['image_url']: label for label in image_labels}

                # 统计信息
                stats = {
                    split_type: {'processed': 0, 'failed': []}
                    for split_type in dir_structure.keys()
                }

                # 处理每张图片
                for idx, train_item in enumerate(train_data, 1):
                    image_name = train_item.get('image_name')
                    image_url = train_item.get('image_url')
                    image_width = train_item.get('width')
                    image_height = train_item.get('height')
                    split_type = train_item.get('type', 'train')

                    if not image_name or not image_url:
                        logger.warning(f"跳过无效数据项: {train_item}")
                        continue

                    # 验证类型有效性
                    if split_type not in dir_structure:
                        logger.warning(f"图片 {image_name} 类型 {split_type} 无效或未启用, 跳过")
                        continue

                    # 获取标注信息
                    label_info = label_map.get(image_url)
                    if not label_info:
                        logger.warning(f"图片 {image_name} 无标注信息, 生成空标注文件")

                    try:
                        # 提取对象名称并验证存在性
                        object_name = self._extract_object_name(image_url, 'munchkin-public')

                        if not storage.exists(object_name):
                            raise FileNotFoundError(f"MinIO 对象不存在: {object_name}")

                        # 从 MinIO 读取并保存到对应类型目录
                        image_path = dir_structure[split_type]['images'] / image_name

                        with storage.open(object_name, 'rb') as src_file:
                            image_path.write_bytes(src_file.read())

                        # 生成 YOLO 标注文件
                        label_file = dir_structure[split_type]['labels'] / f"{image_path.stem}.txt"
                        
                        if label_info:
                            self._write_yolo_label(
                                label_file,
                                label_info,
                                class_names,
                                image_width,
                                image_height
                            )
                        else:
                            # 无标注时生成空文件（符合 YOLO 规范）
                            label_file.touch()

                        stats[split_type]['processed'] += 1
                        logger.info(f"处理进度 [{idx}/{len(train_data)}]: {image_name} ({split_type})")
                        
                    except Exception as e:
                        stats[split_type]['failed'].append({
                            'image': image_name,
                            'error': str(e)
                        })
                        logger.error(
                            f"处理图片失败: {image_name}, "
                            f"对象: {object_name if 'object_name' in locals() else 'N/A'}, "
                            f"错误: {str(e)}"
                        )

                # 检查处理结果
                total_processed = sum(s['processed'] for s in stats.values())
                if total_processed == 0:
                    return Response(
                        {'error': '所有图片处理失败, 无法生成数据集'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
                
                # 生成 data.yaml
                yaml_content = self._generate_data_yaml(
                    class_names, 
                    available_splits=list(dir_structure.keys())
                )
                yaml_path = dataset_root / 'data.yaml'
                yaml_path.write_text(yaml_content, encoding='utf-8')

                # 打包为 ZIP
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                zip_filename = f'yolo_dataset_{instance.id}_{timestamp}.zip'
                zip_path = Path(temp_dir) / zip_filename

                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in dataset_root.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(dataset_root)
                            zipf.write(file_path, arcname)
                
                zip_size_mb = zip_path.stat().st_size / 1024 / 1024
                logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

                # 上传到 MinIO
                with open(zip_path, 'rb') as f:
                    date_prefixed_path = iso_date_prefix(instance, zip_filename)
                    zip_object_path = f'yolo_datasets/{instance.dataset_id}/{date_prefixed_path}'
                    
                    saved_path = storage.save(zip_object_path, f)
                    zip_url = storage.url(saved_path)

                logger.info(f"数据集上传成功: {zip_url}")

                # 更新 meta_data
                instance.meta_data['yolo_dataset_url'] = zip_url
                instance.save(update_fields=['meta_data'])
                
                return Response({
                    'message': '数据集生成成功',
                    'dataset_url': zip_url,
                    'statistics': {
                        split: {
                            'processed': stats[split]['processed'],
                            'failed': len(stats[split]['failed'])
                        } for split in stats.keys()
                    },
                    'failed_details': {
                        k: v['failed'] for k, v in stats.items() if v['failed']
                    } if any(s['failed'] for s in stats.values()) else None,
                    'dataset_size_mb': round(zip_size_mb, 2)
                }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"生成 YOLO 数据集失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'生成失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            

    def _write_yolo_label(self, label_file, label_info, class_names, image_width, image_height):
        """
        写入 YOLO 格式标注文件
        
        YOLO 格式: <class_id> <x_center> <y_center> <width> <height>
        所有坐标归一化到 [0, 1]
        
        Args:
            label_file: 标注文件路径
            label_info: 标注信息，包含 label.rect 列表
            class_names: 类别名称列表
            img_width: 图片宽度（像素）
            img_height: 图片高度（像素）
        """
        if not image_width or not image_height or image_width <= 0 or image_height <= 0:
            logger.warning(f"图片尺寸无效: {image_width}x{image_height}, 无法生成标注")
            label_file.touch()
            return
        
        # 获取rect列表
        label_data = label_info.get('label', {})
        rects = label_data.get('rect', [])

        if not rects:
            logger.debug(f"标注为空, 生成空标注文件: {label_file.name}")
            label_file.touch()
            return
        
        with open(label_file, 'w', encoding='utf-8') as f:
            for rect in rects:
                try:
                    class_label = rect.get('label')
                    if not class_label or class_label not in class_names:
                        logger.warning(f"未知类型 {class_label}, 跳过")
                        continue

                    class_id = class_names.index(class_label)

                    # 获取边界框坐标
                    x = rect.get('x', 0)
                    y = rect.get('y', 0)
                    width = rect.get('width', 0)
                    height = rect.get('height', 0)

                    # 归一化(中心点 + 归一化宽高)
                    x_center = (x + width / 2) / image_width
                    y_center = (y + height / 2) / image_height
                    norm_width = width / image_width
                    norm_height = height / image_height

                    # 坐标裁剪到 [0, 1]
                    x_center = max(0.0, min(1.0, x_center))
                    y_center = max(0.0, min(1.0, y_center))
                    norm_width = max(0.0, min(1.0, norm_width))
                    norm_height = max(0.0, min(1.0, norm_height))

                    # 写入标注行
                    f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_width:.6f} {norm_height:.6f}\n")

                except Exception as e:
                    logger.error(f"处理 rect 失败: {rect}, 错误: {str(e)}")

    def _generate_data_yaml(self, class_names, available_splits=None):
        """
        生成 YOLO 数据集配置文件
        
        Args:
            class_names: 类别名称列表
            available_splits: 可用的数据集分割类型列表
            
        Returns:
            YAML 格式配置字符串
        """
        if available_splits is None:
            available_splits = ['train', 'val', 'test']
        
        yaml_content = """# YOLO Dataset Configuration
# Auto-generated by OpsPilot

path: .
"""
        
        # 根据实际存在的分割类型生成路径
        for split in available_splits:
            yaml_content += f"{split}: images/{split}\n"
        
        yaml_content += "\n# Classes\nnames:\n"
        
        for idx, name in enumerate(class_names):
            yaml_content += f"  {idx}: {name}\n"
        
        return yaml_content



