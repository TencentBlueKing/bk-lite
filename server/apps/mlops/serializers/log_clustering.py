from rest_framework import serializers

from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.log_clustering import *


class LogClusteringDatasetSerializer(AuthSerializer):
    """日志聚类数据集序列化器"""
    permission_key = "dataset.log_clustering_dataset"

    class Meta:
        model = LogClusteringDataset
        fields = "__all__"


class LogClusteringTrainDataSerializer(AuthSerializer):
    """日志聚类训练数据序列化器"""
    permission_key = "dataset.log_clustering_train_data"

    class Meta:
        model = LogClusteringTrainData
        fields = "__all__"
        extra_kwargs = {
            'name': {'required': False},
            'train_data': {'required': False},
            'dataset': {'required': False},
        }
    
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
        当 include_train_data=true 时，后端直接读取文本文件并解析为结构化数据返回
        """
        from apps.core.logger import mlops_logger as logger
        
        representation = super().to_representation(instance)
        
        # 处理 train_data：后端直接读取文本文件
        if self.include_train_data and instance.train_data:
            try:
                # 读取文本文件内容，每行一条日志
                file_content = instance.train_data.read().decode('utf-8')
                lines = file_content.strip().split('\n')
                data_list = [{'log': line} for line in lines if line.strip()]
                
                representation['train_data'] = data_list
                logger.info(f"Successfully loaded train_data for instance {instance.id}: {len(data_list)} logs")
                
            except Exception as e:
                logger.error(f"Failed to read train_data for instance {instance.id}: {e}", exc_info=True)
                representation['train_data'] = []
                representation['error'] = f"读取训练数据失败: {str(e)}"
        elif not self.include_train_data:
            representation.pop("train_data", None)
        
        # 处理 metadata：S3JSONField 自动处理，直接返回对象
        if self.include_metadata and instance.metadata:
            # S3JSONField 会自动从 MinIO 读取并解压
            representation['metadata'] = instance.metadata
        elif not self.include_metadata:
            representation.pop("metadata", None)
        
        return representation


class LogClusteringDatasetReleaseSerializer(AuthSerializer):
    """日志聚类数据集发布版本序列化器"""
    permission_key = "dataset.log_clustering_dataset_release"
    
    # 添加只写字段用于接收文件ID
    train_file_id = serializers.IntegerField(write_only=True, required=False)
    val_file_id = serializers.IntegerField(write_only=True, required=False)
    test_file_id = serializers.IntegerField(write_only=True, required=False)
    
    class Meta:
        model = LogClusteringDatasetRelease
        fields = '__all__'
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
        from apps.core.logger import mlops_logger as logger
        
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
        from apps.core.logger import mlops_logger as logger
        
        dataset = validated_data.get('dataset')
        version = validated_data.get('version')
        name = validated_data.get('name')
        description = validated_data.get('description', '')
        
        try:
            # 验证文件是否存在
            train_obj = LogClusteringTrainData.objects.get(id=train_file_id, dataset=dataset)
            val_obj = LogClusteringTrainData.objects.get(id=val_file_id, dataset=dataset)
            test_obj = LogClusteringTrainData.objects.get(id=test_file_id, dataset=dataset)
            
            # 检查是否已有相同版本的记录（幂等性保护）
            existing = LogClusteringDatasetRelease.objects.filter(
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
            
            release = LogClusteringDatasetRelease.objects.create(**validated_data)
            
            # 触发异步任务
            from apps.mlops.tasks.log_clustering import publish_dataset_release_async
            publish_dataset_release_async.delay(
                release.id,
                train_file_id,
                val_file_id,
                test_file_id
            )
            
            logger.info(f"创建数据集发布任务 - Release ID: {release.id}, Dataset: {dataset.id}, Version: {version}")
            
            return release
            
        except LogClusteringTrainData.DoesNotExist as e:
            logger.error(f"训练数据文件不存在 - {str(e)}")
            raise serializers.ValidationError(f"训练数据文件不存在或不属于该数据集")
        except Exception as e:
            logger.error(f"创建数据集发布任务失败 - {str(e)}", exc_info=True)
            raise serializers.ValidationError(f"创建发布任务失败: {str(e)}")


class LogClusteringTrainJobSerializer(AuthSerializer):
    """
    日志聚类训练任务序列化器
    
    使用双字段方案：
    - hyperopt_config: JSONField，存储在数据库，供API快速返回
    - config_url: FileField，自动同步到MinIO（Model.save()处理）
    """
    permission_key = "dataset.log_clustering_train_job"

    class Meta:
        model = LogClusteringTrainJob
        fields = '__all__'
        extra_kwargs = {
            'config_url': {
                'write_only': True,  # 前端不需要看到 MinIO 路径
                'required': False
            }
        }
    
    def validate(self, attrs):
        """
        验证创建时 dataset_version 必须传入
        """
        # 只在创建时验证（更新时不强制要求）
        if not self.instance and not attrs.get('dataset_version'):
            raise serializers.ValidationError({
                'dataset_version': '创建训练任务时必须指定数据集版本'
            })
        return super().validate(attrs)


class LogClusteringServingSerializer(AuthSerializer):
    """日志聚类服务序列化器"""
    permission_key = "dataset.log_clustering_serving"

    class Meta:
        model = LogClusteringServing
        fields = "__all__"
