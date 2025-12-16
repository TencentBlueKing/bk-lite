from rest_framework import serializers
from django.db import transaction
from django_minio_backend import MinioBackend, iso_date_prefix
import tempfile
import zipfile
import json
from pathlib import Path

from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.timeseries_predict import *
from apps.core.logger import opspilot_logger as logger


class TimeSeriesPredictDatasetSerializer(AuthSerializer):
    """时间序列预测数据集序列化器"""
    permission_key = "dataset.timeseries_predict_dataset"

    class Meta:
        model = TimeSeriesPredictDataset
        fields = "__all__"


class TimeSeriesPredictTrainJobSerializer(AuthSerializer):
    """时间序列预测训练任务序列化器"""
    permission_key = "dataset.timeseries_predict_train_job"

    class Meta:
        model = TimeSeriesPredictTrainJob
        fields = "__all__"


class TimeSeriesPredictTrainHistorySerializer(AuthSerializer):
    """时间序列预测训练历史序列化器"""
    permission_key = "dataset.timeseries_predict_train_history"

    class Meta:
        model = TimeSeriesPredictTrainHistory
        fields = "__all__"


class TimeSeriesPredictTrainDataSerializer(AuthSerializer):
    """时间序列预测训练数据序列化器"""
    permission_key = "dataset.timeseries_predict_train_data"

    class Meta:
        model = TimeSeriesPredictTrainData
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """
        初始化序列化器，从请求上下文中获取 include_train_data 参数
        """
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request:
            self.include_train_data = request.query_params.get('include_train_data', 'false').lower() == 'true'
            self.include_metadata = request.query_params.get('include_metadata', 'false').lower() == 'true'
        else:
            self.include_train_data = False
            self.include_metadata = False

    def to_representation(self, instance):
        """
        自定义返回数据，根据 include_train_data 参数动态控制 train_data 字段
        """
        representation = super().to_representation(instance)
        if not self.include_train_data:
            representation.pop("train_data", None)  # 移除 train_data 字段
        if not self.include_metadata:
            representation.pop("metadata", None)  # 移除 metadata 字段
        return representation

class TimeSeriesPredictServingSerializer(AuthSerializer):
    """时间序列预测服务序列化器"""
    permission_key = "dataset.timeseries_predict_serving"

    class Meta:
        model = TimeSeriesPredictServing
        fields = "__all__"


class TimeSeriesPredictDatasetReleaseSerializer(AuthSerializer):
    """时间序列预测数据集发布版本序列化器"""
    permission_key = "dataset.timeseries_predict_dataset_release"
    
    # 添加只写字段用于接收文件ID
    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = TimeSeriesPredictDatasetRelease
        fields = "__all__"
        extra_kwargs = {
            'name': {'required': False},  # 创建时可选，会自动生成
            'dataset_file': {'required': False},  # 创建时不需要直接提供文件
            'file_size': {'required': False},
            'status': {'required': False},
        }
    
    def create(self, validated_data):
        """
        自定义创建方法，支持从文件ID创建数据集发布版本
        """
        # 提取文件ID
        train_file_id = validated_data.pop('train_file_id', None)
        val_file_id = validated_data.pop('val_file_id', None)
        test_file_id = validated_data.pop('test_file_id', None)
        
        # 如果提供了文件ID，则执行文件打包逻辑
        if train_file_id and val_file_id and test_file_id:
            return self._create_from_files(validated_data, train_file_id, val_file_id, test_file_id)
        else:
            # 否则使用标准创建（适用于直接上传ZIP文件的场景）
            return super().create(validated_data)
    
    def _create_from_files(self, validated_data, train_file_id, val_file_id, test_file_id):
        """
        从训练数据文件ID创建数据集发布版本
        """
        dataset = validated_data.get('dataset')
        version = validated_data.get('version')
        name = validated_data.get('name')
        description = validated_data.get('description', '')
        
        try:
            # 获取训练数据对象
            train_obj = TimeSeriesPredictTrainData.objects.get(id=train_file_id, dataset=dataset)
            val_obj = TimeSeriesPredictTrainData.objects.get(id=val_file_id, dataset=dataset)
            test_obj = TimeSeriesPredictTrainData.objects.get(id=test_file_id, dataset=dataset)
            
            logger.info(f"开始发布数据集 - Dataset: {dataset.id}, Version: {version}, Files: {train_file_id}/{val_file_id}/{test_file_id}")
            
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
                total_samples = train_samples + val_samples + test_samples
                dataset_metadata = {
                    "train_samples": train_samples,
                    "val_samples": val_samples,
                    "test_samples": test_samples,
                    "total_samples": total_samples,
                    "features": ["timestamp", "value"],
                    "data_types": {
                        "timestamp": "datetime",
                        "value": "float"
                    },
                    "split_ratio": {
                        "train": round(train_samples / total_samples, 3) if total_samples > 0 else 0,
                        "val": round(val_samples / total_samples, 3) if total_samples > 0 else 0,
                        "test": round(test_samples / total_samples, 3) if total_samples > 0 else 0
                    },
                    "source": {
                        "type": "manual_selection",
                        "train_file_id": train_file_id,
                        "val_file_id": val_file_id,
                        "test_file_id": test_file_id,
                        "train_file_name": train_obj.name,
                        "val_file_name": val_obj.name,
                        "test_file_name": test_obj.name,
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
                    # 更新 validated_data
                    validated_data['file_size'] = zip_size
                    validated_data['status'] = 'published'
                    validated_data['metadata'] = dataset_metadata
                    
                    if not name:
                        validated_data['name'] = f"{dataset.name}_v{version}"
                    
                    if not description:
                        validated_data['description'] = f"从数据集文件手动发布: {train_obj.name}, {val_obj.name}, {test_obj.name}"
                    
                    release = TimeSeriesPredictDatasetRelease.objects.create(**validated_data)
                    
                    # 手动设置 dataset_file 字段
                    release.dataset_file.name = saved_path
                    release.save(update_fields=['dataset_file'])
                
                logger.info(f"数据集发布成功 - Release ID: {release.id}, 样本数: {train_samples}/{val_samples}/{test_samples}")
                
                return release
                
        except TimeSeriesPredictTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"数据集发布失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"数据集发布失败: {str(e)}")
