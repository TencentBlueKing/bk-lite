# -- coding: utf-8 --
# @File: base_serializers.py.py
# @Time: 2025/11/3 15:55
# @Author: windyzhao
from rest_framework import serializers

class BaseFormatTimeSerializer(serializers.ModelSerializer):
    # 格式化时间字段
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
