# -*- coding: utf-8 -*-
"""
Lab 环境序列化器
"""

from rest_framework import serializers
from apps.lab.models import LabEnv, LabImage, InfraInstance


class LabEnvSerializer(serializers.ModelSerializer):
    """Lab 环境序列化器"""
    
    state_display = serializers.CharField(source='get_state_display', read_only=True)
    ide_image_name = serializers.CharField(source='ide_image.name', read_only=True)
    ide_image_version = serializers.CharField(source='ide_image.version', read_only=True)
    
    # 关联的基础设施实例信息
    infra_instances_info = serializers.SerializerMethodField()
    # 基础设施实例数量（用于列表视图）
    infra_instances_count = serializers.SerializerMethodField()
    
    class Meta:
        model = LabEnv
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'state_display',
                           'ide_image_name', 'ide_image_version', 'endpoint',
                           'infra_instances_info', 'infra_instances_count']
        
    def get_infra_instances_info(self, obj):
        """获取关联的基础设施实例信息"""
        instances = obj.infra_instances.all()
        return [
            {
                'id': instance.id,
                'name': instance.name,
                'status': instance.status,
                'status_display': instance.get_status_display(),
                'image_name': instance.image.name,
                'image_version': instance.image.version,
                'endpoint': instance.endpoint
            }
            for instance in instances
        ]
        
    def get_infra_instances_count(self, obj):
        """获取关联的基础设施实例数量"""
        return obj.infra_instances.count()