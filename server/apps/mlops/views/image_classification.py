from config.drf.viewsets import ModelViewSet

from apps.core.logger import opspilot_logger as logger
from apps.mlops.models.image_classification import *
from apps.mlops.serializers.image_classification import *
from apps.mlops.filters.image_classification import *
from config.drf.pagination import CustomPageNumberPagination
from apps.core.decorators.api_permission import HasPermission
from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.http import FileResponse
from apps.mlops.utils import mlflow_service
from apps.mlops.utils.webhook_client import WebhookClient, WebhookError, WebhookConnectionError, WebhookTimeoutError
import os


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
    """图片分类训练数据视图集（重构：支持ZIP文件上传）"""
    queryset = ImageClassificationTrainData.objects.all()
    serializer_class = ImageClassificationTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ImageClassificationTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.image_classification_train_data"

    @HasPermission("image_classification_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("image_classification_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("image_classification_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        """
        删除训练数据实例，自动删除关联的 MinIO ZIP 文件
        """
        try:
            instance = self.get_object()
            instance_id = instance.id
            instance_name = instance.name
            
            # train_data FileField 会在模型的 save() 方法中自动清理
            logger.info(f"开始删除训练数据实例: ID={instance_id}, 名称={instance_name}")
            
            # 删除实例（模型会自动清理文件）
            super().destroy(request, *args, **kwargs)
            
            logger.info(f"训练数据实例删除完成: ID={instance_id}")
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except Exception as e:
            logger.error(f"删除训练数据失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'删除失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @HasPermission("image_classification_train_data-Add")
    def create(self, request, *args, **kwargs):
        """
        创建训练数据：上传 ZIP 压缩包 + metadata
        """
        return super().create(request, *args, **kwargs)

    @HasPermission("image_classification_train_data-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新训练数据：可替换 ZIP 文件或更新 metadata
        """
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='download')
    @HasPermission("image_classification_train_data-View")
    def download(self, request, pk=None):
        """下载训练数据 ZIP 文件"""
        try:
            instance = self.get_object()
            
            if not instance.train_data:
                return Response(
                    {'error': '训练数据文件不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            file = instance.train_data.open('rb')
            filename = f"{instance.name}_{instance.id}.zip"
            
            response = FileResponse(file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = instance.train_data.size
            
            logger.info(f"下载训练数据: {instance.name} (ID: {instance.id})")
            return response
            
        except Exception as e:
            logger.error(f"下载训练数据失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'], url_path='download_metadata')
    @HasPermission("image_classification_train_data-View")
    def download_metadata(self, request, pk=None):
        """下载训练数据 metadata JSON 文件"""
        try:
            instance = self.get_object()
            
            if not instance.metadata:
                return Response(
                    {'error': 'Metadata 不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 返回 JSON 格式的 metadata
            return Response(instance.metadata, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"获取 metadata 失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImageClassificationDatasetReleaseViewSet(ModelViewSet):
    """图片分类数据集发布版本视图集"""
    queryset = ImageClassificationDatasetRelease.objects.all()
    serializer_class = ImageClassificationDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ImageClassificationDatasetReleaseFilter
    ordering = ("-created_at",)
    permission_key = "dataset.image_classification_dataset_release"

    @HasPermission("image_classification_dataset_releases-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("image_classification_dataset_releases-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("image_classification_dataset_releases-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("image_classification_dataset_releases-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("image_classification_dataset_releases-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='download')
    @HasPermission("image_classification_dataset_releases-View")
    def download(self, request, *args, **kwargs):
        """下载数据集发布版本的压缩包"""
        try:
            instance = self.get_object()
            
            if not instance.dataset_file:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            file = instance.dataset_file.open('rb')
            filename = f"{instance.dataset.name}_{instance.version}.zip"
            
            response = FileResponse(file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"下载数据集版本: {instance.dataset.name} - {instance.version}")
            return response
            
        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='archive')
    @HasPermission("image_classification_dataset_releases-Edit")
    def archive(self, request, pk=None):
        """归档数据集版本"""
        try:
            instance = self.get_object()
            
            if instance.status == 'archived':
                return Response(
                    {'error': '数据集版本已经是归档状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            instance.status = 'archived'
            instance.save(update_fields=['status'])
            
            logger.info(f"数据集版本已归档: {instance.dataset.name} - {instance.version}")
            
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"归档数据集版本失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'归档失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='unarchive')
    @HasPermission("image_classification_dataset_releases-Edit")
    def unarchive(self, request, pk=None):
        """恢复归档的数据集版本"""
        try:
            instance = self.get_object()
            
            if instance.status != 'archived':
                return Response(
                    {'error': '只能恢复归档状态的数据集版本'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            instance.status = 'published'
            instance.save(update_fields=['status'])
            
            logger.info(f"数据集版本已恢复: {instance.dataset.name} - {instance.version}")
            
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"恢复数据集版本失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'恢复失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImageClassificationTrainJobViewSet(ModelViewSet):
    """图片分类训练任务视图集"""
    queryset = ImageClassificationTrainJob.objects.all()
    serializer_class = ImageClassificationTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ImageClassificationTrainJobFilter
    ordering = ("-created_at",)
    permission_key = "train_tasks.image_classification_train_job"
    
    # MLflow 前缀
    MLFLOW_PREFIX = "ImageClassification"

    @HasPermission("image_classification_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("image_classification_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("image_classification_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("image_classification_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("image_classification_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='train')
    @HasPermission("image_classification_train_jobs-Train")
    def train(self, request, pk=None):
        """
        启动图片分类训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status == 'running':
                return Response(
                    {'error': '训练任务已在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 获取环境变量
            bucket = os.getenv("MINIO_PUBLIC_BUCKETS", "munchkin-public")
            minio_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "")
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
            minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")

            if not minio_endpoint:
                return Response(
                    {'error': 'MinIO 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            if not mlflow_tracking_uri:
                return Response(
                    {'error': 'MLflow 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                ) 
            
            if not minio_access_key or not minio_secret_key:
                return Response(
                    {'error': 'MinIO 访问凭证未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 检查必要字段
            if not train_job.dataset_release or not train_job.dataset_release.dataset_file:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not train_job.config_url:
                return Response(
                    {'error': '训练配置文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id
            )
            
            logger.info(f"启动图片分类训练任务: {job_id}")
            logger.info(f"  Dataset: {train_job.dataset_release.dataset_file.name}")
            logger.info(f"  Config: {train_job.config_url.name}")
            
            # 调用 WebhookClient 启动训练
            WebhookClient.train(
                job_id=job_id,
                bucket=bucket,
                dataset=train_job.dataset_release.dataset_file.name,
                config=train_job.config_url.name,
                minio_endpoint=minio_endpoint,
                mlflow_tracking_uri=mlflow_tracking_uri,
                minio_access_key=minio_access_key,
                minio_secret_key=minio_secret_key,
                train_image="image-classification:latest"  # YOLO 训练镜像
            )
            
            # 更新任务状态
            train_job.status = 'running'
            train_job.save(update_fields=['status'])
            
            logger.info(f"图片分类训练任务已启动: {job_id}")
            
            return Response({
                'message': '训练任务已启动',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'algorithm': train_job.algorithm
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动训练任务失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'启动训练任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='stop')
    @HasPermission("image_classification_train_jobs-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止图片分类训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status != 'running':
                return Response(
                    {'error': '训练任务未在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建训练任务标识
            job_id = mlflow_service.build_job_id(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id
            )
            
            logger.info(f"停止图片分类训练任务: {job_id}")
            
            # 调用 WebhookClient 停止任务（默认删除容器）
            result = WebhookClient.stop(job_id)
            
            # 更新任务状态
            train_job.status = 'pending'
            train_job.save(update_fields=['status'])
            
            logger.info(f"图片分类训练任务已停止: {job_id}")
            
            return Response({
                'message': '训练任务已停止',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止训练任务失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'停止训练任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'], url_path='model_versions')
    @HasPermission("image_classification_train_jobs-View")
    def get_model_versions(self, request, pk=None):
        """
        获取训练任务对应模型的所有版本列表（从MLflow）
        """
        try:
            train_job = self.get_object()
            
            # 构造模型名称：ImageClassification_YOLOv11n_123
            model_name = mlflow_service.build_model_name(
                prefix=self.MLFLOW_PREFIX,
                algorithm=train_job.algorithm,
                train_job_id=train_job.id
            )
            
            # 查询模型版本
            version_data = mlflow_service.get_model_versions(model_name)
            
            if not version_data:
                logger.info(f"模型未找到版本: {model_name}")
                return Response({
                    'model_name': model_name,
                    'versions': [],
                    'total': 0
                })
            
            logger.info(f"获取模型版本列表成功: {model_name}, 共 {len(version_data)} 个版本")
            
            return Response({
                'model_name': model_name,
                'total': len(version_data),
                'versions': version_data
            })
            
        except Exception as e:
            logger.error(f"获取模型版本列表失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取模型版本列表失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='download_model/(?P<run_id>[^/]+)')
    @HasPermission("image_classification_train_jobs-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件
        
        Args:
            run_id: MLflow run ID
        """
        try:
            logger.info(f"开始下载模型: run_id={run_id}")
            
            # 下载模型并打包为 ZIP
            zip_buffer = mlflow_service.download_model_artifact(
                run_id=run_id,
                artifact_path="model"
            )
            
            # 构造文件名
            filename = f"model_{run_id}.zip"
            
            # 返回文件响应
            from django.http import HttpResponse
            response = HttpResponse(
                zip_buffer.getvalue(),
                content_type='application/zip'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Length'] = len(zip_buffer.getvalue())
            
            logger.info(f"模型下载成功: run_id={run_id}, size={len(zip_buffer.getvalue())} bytes")
            return response
            
        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载模型失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ImageClassificationServingViewSet(ModelViewSet):
    """图片分类服务视图集"""
    queryset = ImageClassificationServing.objects.all()
    serializer_class = ImageClassificationServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = ImageClassificationServingFilter
    ordering = ("-created_at",)
    permission_key = "serving.image_classification_serving"
    
    # MLflow 前缀
    MLFLOW_PREFIX = "ImageClassification"

    @HasPermission("image_classification_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("image_classification_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("image_classification_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("image_classification_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("image_classification_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='start')
    @HasPermission("image_classification_servings-Start")
    def start(self, request, *args, **kwargs):
        """
        启动图片分类 serving 服务
        """
        try:
            serving = self.get_object()
            
            # 获取环境变量
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            if not mlflow_tracking_uri:
                return Response(
                    {'error': '环境变量 MLFLOW_TRACKER_URL 未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建 serving ID
            serving_id = f"ImageClassification_Serving_{serving.id}"
            
            logger.info(f"启动图片分类 serving 服务: {serving_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}")
            
            try:
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(
                    serving_id, 
                    mlflow_tracking_uri, 
                    model_uri, 
                    port=serving.port,
                    train_image="image-classification:latest"  # YOLO 推理镜像
                )
                
                # 正常启动成功，仅更新容器信息
                serving.container_info = result
                serving.save(update_fields=['container_info'])
                
                logger.info(f"图片分类 Serving 服务已启动: {serving_id}, Port: {result.get('port')}")
                
                return Response({
                    'message': '服务已启动',
                    'serving_id': serving_id,
                    'container_info': result
                })
                
            except WebhookError as e:
                error_msg = str(e)
                
                # 处理端口冲突
                if '端口已被占用' in error_msg or 'port is already allocated' in error_msg:
                    return Response(
                        {'error': f'端口 {serving.port} 已被占用，请选择其他端口'},
                        status=status.HTTP_409_CONFLICT
                    )
                
                # 处理模型不存在
                if 'Model' in error_msg and 'not found' in error_msg:
                    return Response(
                        {'error': f'模型 {model_uri} 不存在，请确认模型版本正确'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                raise
                
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动 serving 失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动图片分类 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'启动服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='stop')
    @HasPermission("image_classification_servings-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止图片分类 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()
            
            # 构建 serving ID
            serving_id = f"ImageClassification_Serving_{serving.id}"
            
            logger.info(f"停止图片分类 serving 服务: {serving_id}")
            
            # 调用 WebhookClient 停止服务（默认删除容器）
            result = WebhookClient.stop(serving_id)
            
            logger.info(f"图片分类 Serving 服务已停止: {serving_id}")
            
            return Response({
                'message': '服务已停止并删除',
                'serving_id': serving_id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止 serving 失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止图片分类 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'停止服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='remove')
    @HasPermission("image_classification_servings-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除图片分类 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()
            
            # 构建 serving ID
            serving_id = f"ImageClassification_Serving_{serving.id}"
            
            logger.info(f"删除图片分类 serving 容器: {serving_id}")
            
            # 调用 WebhookClient 删除容器
            result = WebhookClient.remove(serving_id)
            
            # 更新容器信息（status 由用户控制，不修改）
            serving.container_info = {
                "status": "success",
                "id": serving_id,
                "state": "removed",
                "message": "容器已删除"
            }
            serving.save(update_fields=['container_info'])
            
            logger.info(f"图片分类 Serving 容器已删除: {serving_id}")
            
            return Response({
                'message': '容器已删除',
                'serving_id': serving_id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"删除容器失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"删除图片分类 serving 容器失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'删除容器失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI
        
        Args:
            serving: ImageClassificationServing 实例
        
        Returns:
            str: MLflow model URI
        
        Raises:
            ValueError: 解析失败时抛出
        """
        train_job = serving.train_job
        model_name = mlflow_service.build_model_name(
            prefix=self.MLFLOW_PREFIX,
            algorithm=train_job.algorithm,
            train_job_id=train_job.id
        )
        
        return mlflow_service.resolve_model_uri(model_name, serving.model_version)

