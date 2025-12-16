# -*- coding: utf-8 -*-
"""
基础设施实例序列化器
"""

from rest_framework import serializers
from apps.core.utils.serializers import AuthSerializer
from apps.lab.models import InfraInstance


class InfraInstanceSerializer(AuthSerializer):
    """基础设施实例序列化器"""
    permission_key = "dataset.lab_labenv_infra_instance"
    
    class Meta:
        model = InfraInstance
        fields = '__all__'