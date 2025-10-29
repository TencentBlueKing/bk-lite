# -*- coding: utf-8 -*-
"""
基础设施实例序列化器
"""

from rest_framework import serializers
from apps.lab.models import InfraInstance


class InfraInstanceSerializer(serializers.ModelSerializer):
    """基础设施实例序列化器"""
    
    class Meta:
        model = InfraInstance
        fields = '__all__'