# -*- coding: utf-8 -*-
"""
Lab 环境视图
"""

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from apps.lab.models import LabEnv
from apps.lab.serializers import (
    LabEnvSerializer,
)
from apps.lab.utils.lab_utils import LabUtils


class LabEnvViewSet(viewsets.ModelViewSet):
    """
    Lab 环境视图集
    
    提供实验环境的增删改查、启动、停止功能
    """
    queryset = LabEnv.objects.select_related('ide_image').prefetch_related('infra_instances').order_by('-created_at')
    serializer_class = LabEnvSerializer
    
    # 过滤和搜索
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['state', 'ide_image', 'created_by']
    search_fields = ['name', 'description', 'ide_image__name']
    ordering_fields = ['created_at', 'updated_at', 'name']
    ordering = ['-created_at']
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """启动 Lab 环境"""
        lab_env = self.get_object()
        
        if lab_env.state == 'running':
            return Response(
                {'detail': 'Lab 环境已经在运行中'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 使用 LabUtils 启动环境
        result = LabUtils.start_lab(lab_env.id)
        
        return Response({
            'detail': 'Lab 环境启动命令已发送',
            'state': lab_env.state,
        })
        
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """停止 Lab 环境"""
        lab_env = self.get_object()
        
        if lab_env.state == 'stopped':
            return Response(
                {'detail': 'Lab 环境已经停止'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 使用 LabUtils 停止环境
        result = LabUtils.stop_lab(lab_env.id)
        
        return Response({
            'detail': 'Lab 环境停止命令已发送',
            'state': lab_env.state,
        })
        
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """重启 Lab 环境"""
        lab_env = self.get_object()
        
        # 先停止再启动
        LabUtils.stop_lab(lab_env.id)
        result = LabUtils.start_lab(lab_env.id)
        
        return Response({
            'detail': 'Lab 环境重启命令已发送',
            'state': lab_env.state,
        })
        
    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """获取环境详细状态"""
        lab_env = self.get_object()
        
        # 使用 LabUtils 获取状态
        status_data = LabUtils.get_lab_status(lab_env.id)
        
        return Response(status_data)