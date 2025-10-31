from config.drf.viewsets import ModelViewSet

from apps.core.logger import opspilot_logger as logger
from apps.mlops.models.image_classification import *
from apps.mlops.serializers.image_classification import *
from apps.mlops.filters.image_classification import *
from config.drf.pagination import CustomPageNumberPagination
from apps.core.decorators.api_permission import HasPermission
from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from django_minio_backend import MinioBackend, iso_date_prefix
from django.conf import settings

class ImageClassificationDatasetViewSet(ModelViewSet):
  queryset = ImageClassificationDataset.objects.all()
  serializer_class = ImageClassificationDatasetSerializer
  filterset_class = ImageClassificationDatasetFilter
  pagination_class = CustomPageNumberPagination
  ordering = "-id"
  permission_key = "dataset.image_classification_dataset"
  
  @HasPermission("image_classification_datasets-View")
  def list(self, request, *args, **kwargs):
      return super().list(request, *args, **kwargs)

  @HasPermission("image_classification_datasets-View")
  def retrieve(self, request, *args, **kwargs):
      return super().retrieve(request, *args, **kwargs)

  @HasPermission("image_classification_datasets-Delete")
  def destroy(self, request, *args, **kwargs):
      return super().destroy(request, *args, **kwargs)

  @HasPermission("image_classification_datasets-Add")
  def create(self, request, *args, **kwargs):
      return super().create(request, *args, **kwargs)

  @HasPermission("image_classification_datasets-Edit")
  def update(self, request, *args, **kwargs):
      return super().update(request, *args, **kwargs)
  
class ImageClassificationTrainDataViewSet(ModelViewSet):
    queryset = ImageClassificationTrainData.objects.all()
    serializer_class = ImageClassificationTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ImageClassificationTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.classification_train_data"

    @HasPermission("classification_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("classification_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("classification_train_data-Delete")
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
                        'message': '实例已删除,但部分文件删除失败',
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

    @HasPermission("classification_train_data-Add")
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
                        'image_label': []
                    })
                }
                
                serializer = self.get_serializer(data=instance_data)
                serializer.is_valid(raise_exception=True)
                instance = serializer.save()
                
                # 逐个上传图片到 MinIO
                for idx, file in enumerate(file_list, 1):
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
                        'batch_index': idx,
                        'batch_total': len(file_list)
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

    @HasPermission("classification_train_data-Edit")
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
                    file_path = iso_date_prefix(instance, file.name)
                    saved_path = storage.save(file_path, file)
                    file_url = storage.url(saved_path)
                    
                    image_info = {
                        'image_name': file.name,
                        'image_size': file.size,
                        'content_type': getattr(file, 'content_type', 'unknown'),
                        'image_url': file_url,
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