from rest_framework import serializers

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
    """
    时间序列预测训练任务序列化器
    
    使用双字段方案：
    - hyperopt_config: JSONField，存储在数据库，供API快速返回
    - config_url: FileField，自动同步到MinIO（Model.save()处理）
    """
    permission_key = "dataset.timeseries_predict_train_job"

    class Meta:
        model = TimeSeriesPredictTrainJob
        fields = '__all__'
        extra_kwargs = {
            'config_url': {
                'write_only': True,  # 前端不需要看到 MinIO 路径
                'required': False
            }
        }


class TimeSeriesPredictTrainHistorySerializer(AuthSerializer):
    """
    时间序列预测训练历史序列化器
    
    使用双字段方案：
    - hyperopt_config: JSONField，存储在数据库，供API快速返回
    - config_url: FileField，自动同步到MinIO（Model.save()处理）
    """
    permission_key = "dataset.timeseries_predict_train_history"

    class Meta:
        model = TimeSeriesPredictTrainHistory
        fields = "__all__"
        extra_kwargs = {
            'config_url': {
                'write_only': True,  # 前端不需要看到 MinIO 路径
                'required': False
            }
        }


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
        从训练数据文件ID创建数据集发布版本（异步）
        
        创建 pending 状态的记录，触发 Celery 任务进行异步处理
        """
        dataset = validated_data.get('dataset')
        version = validated_data.get('version')
        name = validated_data.get('name')
        description = validated_data.get('description', '')
        
        try:
            # 验证文件是否存在
            train_obj = TimeSeriesPredictTrainData.objects.get(id=train_file_id, dataset=dataset)
            val_obj = TimeSeriesPredictTrainData.objects.get(id=val_file_id, dataset=dataset)
            test_obj = TimeSeriesPredictTrainData.objects.get(id=test_file_id, dataset=dataset)
            
            # 检查是否已有相同版本的记录（幂等性保护）
            existing = TimeSeriesPredictDatasetRelease.objects.filter(
                dataset=dataset,
                version=version
            ).exclude(status='failed').first()
            
            if existing:
                logger.info(f"数据集版本已存在 - Dataset: {dataset.id}, Version: {version}, Status: {existing.status}")
                return existing
            
            # 创建 pending 状态的发布记录
            validated_data['status'] = 'pending'
            validated_data['file_size'] = 0
            validated_data['metadata'] = {}
            
            if not name:
                validated_data['name'] = f"{dataset.name}_v{version}"
            
            if not description:
                validated_data['description'] = f"从数据集文件手动发布: {train_obj.name}, {val_obj.name}, {test_obj.name}"
            
            release = TimeSeriesPredictDatasetRelease.objects.create(**validated_data)
            
            # 触发异步任务
            from apps.mlops.tasks.timeseries import publish_dataset_release_async
            publish_dataset_release_async.delay(
                release.id,
                train_file_id,
                val_file_id,
                test_file_id
            )
            
            logger.info(f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}")
            
            return release
            
        except TimeSeriesPredictTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建发布任务失败: {str(e)}")
