# -*- coding: utf-8 -*-
"""
基础设施实例视图 - 简化版本
"""

import logging
from rest_framework import viewsets
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.lab.models import InfraInstance
from apps.lab.serializers import InfraInstanceSerializer

logger = logging.getLogger(__name__)


class InfraInstanceViewSet(viewsets.ModelViewSet):
    """
    基础设施实例视图集 - 简化版本
    
    提供基础设施实例的增删改查功能
    """
    queryset = InfraInstance.objects.select_related('image').order_by('-created_at')
    serializer_class = InfraInstanceSerializer
    
    # 过滤和搜索
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'image', 'created_by']
    search_fields = ['name', 'image__name']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']