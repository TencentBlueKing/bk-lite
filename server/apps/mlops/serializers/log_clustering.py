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
        from apps.core.logger import opspilot_logger as logger
        
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


class LogClusteringServingSerializer(AuthSerializer):
    """日志聚类服务序列化器"""
    permission_key = "dataset.log_clustering_serving"

    class Meta:
        model = LogClusteringServing
        fields = "__all__"
