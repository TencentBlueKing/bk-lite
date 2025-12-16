from apps.core.utils.serializers import AuthSerializer
from apps.mlops.models.image_classification import *
from rest_framework import serializers
from apps.core.logger import opspilot_logger as logger

class ImageClassificationDatasetSerializer(AuthSerializer):
  """图片分类任务数据集序列化器"""
  permission_key = "dataset.image_classification_dataset"

  class Meta:
    model = ImageClassificationDataset
    fields = "__all__"

class ImageClassificationTrainDataSerializer(AuthSerializer):
  """分类任务训练数据序列化器"""
  permission_key = "dataset.image_classification_train_data"

  class Meta:
    model = ImageClassificationTrainData
    fields = "__all__"
    extra_kwargs = {
      'train_data': {'required': False, 'default': list},
      'meta_data': {'required': False}
    }
  
  def __init__(self, *args, **kwargs):
    """初始化序列化器,从请求上下文中获取参数"""
    super().__init__(*args, **kwargs)
    request = self.context.get('request')
    if request:
      self.include_train_data = request.query_params.get('include_train_data', 'false').lower() == 'true'
      self.include_metadata = request.query_params.get('include_metadata', 'false').lower() == 'true'
    else:
      self.include_train_data = False
      self.include_metadata = False

  def to_representation(self, instance):
    """自定义返回数据,根据参数动态控制字段"""
    representation = super().to_representation(instance)
    if not self.include_train_data:
      representation.pop('train_data', None)
    if not self.include_metadata:
      representation.pop('meta_data', None)
    return representation
     

 