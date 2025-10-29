# -*- coding: utf-8 -*-
"""
Lab 镜像视图
"""

from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.lab.models import LabImage
from apps.lab.serializers import LabImageSerializer


class LabImageViewSet(viewsets.ModelViewSet):
    """
    Lab 镜像视图集
    
    提供镜像的增删改查功能
    """
    queryset = LabImage.objects.all().order_by('-created_at')
    serializer_class = LabImageSerializer
    
    # 过滤和搜索
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['image_type', 'created_by']
    search_fields = ['name', 'version', 'description', 'image']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']