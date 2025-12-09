from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.timeseries_predict import *
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from django.core.files.base import ContentFile
from django_minio_backend import MinioBackend, iso_date_prefix
import zipfile
import tempfile
import os
from pathlib import Path

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.timeseries_predict import *
from apps.mlops.serializers.timeseries_predict import *
from config.drf.pagination import CustomPageNumberPagination


class TimeSeriesPredictDatasetViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDataset.objects.all()
    serializer_class = TimeSeriesPredictDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset"

    @HasPermission("timeseries_predict_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainJobViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainJob.objects.all()
    serializer_class = TimeSeriesPredictTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_job"

    @HasPermission("timeseries_predict_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)
    
    @action(detail=True, methods=['post'], url_path='release_dataset')
    @HasPermission("timeseries_predict_train_jobs-Edit")
    def release_dataset(self, request, *args, **kwargs):
        """
        从训练任务创建数据集版本发布
        将训练任务关联的训练、验证、测试数据从MinIO下载，打包成ZIP文件后上传
        
        此接口作为便捷方式，从已有训练任务快速生成数据集版本
        推荐使用独立的 DatasetRelease 接口直接发布数据集版本
        """
        try:
            train_job = self.get_object()
            version = request.data.get('version')
            name = request.data.get('name')
            description = request.data.get('description', '')

            if not version:
                return Response(
                    {'error': '请提供版本号'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 获取数据集
            if not train_job.train_data_id or not train_job.train_data_id.dataset:
                return Response(
                    {'error': '训练任务未关联数据集'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            dataset = train_job.train_data_id.dataset

            # 检查版本是否已存在
            if TimeSeriesPredictDatasetRelease.objects.filter(
                dataset=dataset,
                version=version
            ).exists():
                return Response(
                    {'error': f'数据集 {dataset.name} 的版本 {version} 已存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # 获取关联的训练数据
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            if not all([train_obj, val_obj, test_obj]):
                return Response(
                    {'error': '训练任务缺少必要的训练/验证/测试数据'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"开始发布数据集 - Dataset: {dataset.id}, Version: {version}, from TrainJob: {train_job.id}")

            storage = MinioBackend(bucket_name='munchkin-public')

            # 创建临时目录用于存放文件
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # 通过 ORM FileField 直接读取 MinIO 文件
                files_info = [
                    (train_obj.train_data, 'train_data.csv'),
                    (val_obj.train_data, 'val_data.csv'),
                    (test_obj.train_data, 'test_data.csv'),
                ]

                # 统计数据集信息
                import json
                import hashlib
                train_samples = 0
                val_samples = 0
                test_samples = 0
                
                for file_field, filename in files_info:
                    if file_field and file_field.name:
                        try:
                            # 使用 FileField.open() 直接读取 MinIO 文件
                            with file_field.open('rb') as f:
                                file_content = f.read()
                            
                            # 保存到临时目录
                            local_file_path = temp_path / filename
                            with open(local_file_path, 'wb') as f:
                                f.write(file_content)
                            
                            # 统计样本数（CSV文件行数-1表头）
                            line_count = file_content.decode('utf-8').count('\n')
                            sample_count = max(0, line_count - 1)
                            
                            if 'train' in filename:
                                train_samples = sample_count
                            elif 'val' in filename:
                                val_samples = sample_count
                            elif 'test' in filename:
                                test_samples = sample_count
                            
                            logger.info(f"下载文件成功: {filename}, 大小: {len(file_content)} bytes, 样本数: {sample_count}")
                        except Exception as e:
                            logger.error(f"下载文件失败: {filename} - {str(e)}")
                            raise

                # 生成数据集元信息（纯净版本，不包含超参数）
                dataset_metadata = {
                    "train_samples": train_samples,
                    "val_samples": val_samples,
                    "test_samples": test_samples,
                    "total_samples": train_samples + val_samples + test_samples,
                    "features": ["timestamp", "value"],
                    "data_types": {
                        "timestamp": "datetime",
                        "value": "float"
                    },
                    "split_ratio": {
                        "train": round(train_samples / (train_samples + val_samples + test_samples), 3) if (train_samples + val_samples + test_samples) > 0 else 0,
                        "val": round(val_samples / (train_samples + val_samples + test_samples), 3) if (train_samples + val_samples + test_samples) > 0 else 0,
                        "test": round(test_samples / (train_samples + val_samples + test_samples), 3) if (train_samples + val_samples + test_samples) > 0 else 0
                    },
                    "source": {
                        "type": "train_job",
                        "train_job_id": train_job.id,
                        "train_job_name": train_job.name,
                        "created_at": train_job.created_at.isoformat() if hasattr(train_job.created_at, 'isoformat') else str(train_job.created_at)
                    }
                }
                
                # 保存数据集元信息到临时文件
                metadata_file = temp_path / 'dataset_metadata.json'
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(dataset_metadata, f, ensure_ascii=False, indent=2)

                # 创建ZIP压缩包
                zip_filename = f"timeseries_dataset_{dataset.name}_{version}.zip"
                zip_path = temp_path / zip_filename

                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for file_path in temp_path.iterdir():
                        if file_path != zip_path:
                            zipf.write(file_path, file_path.name)

                zip_size = zip_path.stat().st_size
                zip_size_mb = zip_size / 1024 / 1024
                logger.info(f"数据集打包完成: {zip_filename}, 大小: {zip_size_mb:.2f} MB")

                # 上传ZIP文件到MinIO
                with open(zip_path, 'rb') as f:
                    date_prefixed_path = iso_date_prefix(dataset, zip_filename)
                    zip_object_path = f'timeseries_datasets/{dataset.id}/{date_prefixed_path}'
                    
                    saved_path = storage.save(zip_object_path, f)
                    zip_url = storage.url(saved_path)

                logger.info(f"数据集上传成功: {zip_url}")

                # 创建发布记录
                with transaction.atomic():
                    release = TimeSeriesPredictDatasetRelease.objects.create(
                        name=name or f"{dataset.name}_v{version}",
                        description=description or f"从训练任务 {train_job.name} 自动生成",
                        dataset=dataset,
                        version=version,
                        file_size=zip_size,
                        status='published',
                        metadata=dataset_metadata,  # 保存数据集元信息
                        created_by=request.user.username,
                        updated_by=request.user.username,
                    )
                    
                    # 手动设置 dataset_file 字段
                    release.dataset_file.name = saved_path
                    release.save(update_fields=['dataset_file'])

                logger.info(f"数据集发布成功 - Release ID: {release.id}, 样本数: {train_samples}/{val_samples}/{test_samples}")

                return Response({
                    'message': '数据集发布成功',
                    'release_id': release.id,
                    'dataset_id': dataset.id,
                    'dataset_name': dataset.name,
                    'version': version,
                    'file_size': zip_size,
                    'file_url': zip_url,
                    'metadata': dataset_metadata  # 返回元信息
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"数据集发布失败 - TrainJobID: {kwargs.get('pk')} - {str(e)}", exc_info=True)
            return Response(
                {'error': f'数据集发布失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='get_file')
    @HasPermission("timeseries_predict_train_jobs-View,timeseries_predict_datasets-File View,timeseries_predict_train_data-View")
    def get_file(self, request, *args, **kwargs):
        try:
            train_job = self.get_object()
            train_obj = train_job.train_data_id
            val_obj = train_job.val_data_id
            test_obj = train_job.test_data_id

            def mergePoints(data_obj, filename):
                train_data = list(data_obj.train_data) if hasattr(data_obj, 'train_data') else []
                columns = ['timestamp', 'value']

                return {
                    "data": train_data,
                    "columns": columns,
                    "filename": filename
                }

            return Response(
                [
                    mergePoints(train_obj, 'train_file.csv'),
                    mergePoints(val_obj, 'val_file.csv'),
                    mergePoints(test_obj, 'test_file.csv'),
                    {
                        "data": train_job.hyperopt_config,
                        "columns": [],
                        "filename": "hyperopt_config.json"
                    }
                ]
            )
        
        except Exception as e:
            logger.error(f"获取训练文件失败 - TrainJobID: {kwargs.get('pk')} - {str(e)}")
            return Response(
                {'error': f'获取文件信息失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TimeSeriesPredictTrainHistoryViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainHistory.objects.all()
    serializer_class = TimeSeriesPredictTrainHistorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainHistoryFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_history"

    @HasPermission("timeseries_predict_train_history-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainDataViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainData.objects.all()
    serializer_class = TimeSeriesPredictTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_data"

    @HasPermission("timeseries_predict_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='release')
    @HasPermission("timeseries_predict_train_data-Release")
    def release_file(self, request, *args, **kwargs):
        pass


class TimeSeriesPredictServingViewSet(ModelViewSet):
    queryset = TimeSeriesPredictServing.objects.all()
    serializer_class = TimeSeriesPredictServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictServingFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_serving"

    @HasPermission("timeseries_predict_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictDatasetReleaseViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDatasetRelease.objects.all()
    serializer_class = TimeSeriesPredictDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetReleaseFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset_release"

    @HasPermission("timeseries_predict_dataset_releases-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='download')
    @HasPermission("timeseries_predict_dataset_releases-View")
    def download(self, request, *args, **kwargs):
        """
        下载数据集版本的 ZIP 文件
        """
        from django.http import FileResponse
        
        try:
            release = self.get_object()
            
            if not release.dataset_file or not release.dataset_file.name:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 获取文件
            file = release.dataset_file.open('rb')
            filename = f"{release.dataset.name}_{release.version}.zip"
            
            response = FileResponse(file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"下载数据集版本: {release.id} - {filename}")
            
            return response
            
        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='archive')
    @HasPermission("timeseries_predict_dataset_releases-Edit")
    def archive(self, request, *args, **kwargs):
        """
        归档数据集版本（将状态改为 archived）
        """
        try:
            release = self.get_object()
            
            # 可以扩展 status 选项，添加 archived
            # 暂时使用 pending 表示归档
            release.status = 'pending'
            release.description = f"[已归档] {release.description or ''}"
            release.save(update_fields=['status', 'description'])
            
            logger.info(f"归档数据集版本: {release.id}")
            
            return Response({
                'message': '归档成功',
                'release_id': release.id
            })
            
        except Exception as e:
            logger.error(f"归档失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'归档失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

