# -*- coding: utf-8 -*-
"""
Lab 镜像序列化器
"""

from rest_framework import serializers
from apps.lab.models import LabImage
from apps.core.utils.serializers import AuthSerializer


class LabImageSerializer(AuthSerializer):
    """Lab 镜像序列化器"""
    
    permission_key = "dataset.lab_labimage"
    image_type_display = serializers.CharField(source='get_image_type_display', read_only=True)
    
    class Meta:
        model = LabImage
        fields = '__all__'
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at', 'image_type_display']