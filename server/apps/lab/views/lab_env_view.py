# -*- coding: utf-8 -*-
"""
Lab 环境视图
"""

import os
import requests
import yaml
from rest_framework import viewsets, status
from config.drf.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.core.logger import opspilot_logger as logger

from apps.lab.models import LabEnv
from apps.lab.serializers import (
    LabEnvSerializer,
)
from apps.lab.utils.lab_utils import LabUtils
from apps.lab.utils.compose_generator import ComposeGenerator


class LabEnvViewSet(ModelViewSet):
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
    
    @action(detail=True, methods=['post'])
    def setup(self, request, pk=None):
        """
        配置 Lab 环境的 Docker Compose
        生成 docker-compose 配置并通过 webhook 发送到 compose 服务
        """
        lab_env = self.get_object()
        
        try:
            # 使用 ComposeGenerator 生成 docker-compose 配置
            compose_config = ComposeGenerator.generate(lab_env)
            
            # 获取 webhook 基础 URL
            webhook_base_url = os.getenv('WEBHOOK', 'http://localhost:8080/compose/')
            if not webhook_base_url.endswith('/'):
                webhook_base_url += '/'
            
            setup_url = f"{webhook_base_url}setup"
            
            # 准备请求数据
            payload = {
                "id": f"lab-env-{lab_env.id}",
                "compose": compose_config
            }
            
            logger.info(f"正在配置 Lab 环境 {lab_env.name} (ID: {lab_env.id})")
            logger.debug(f"Docker Compose 配置:\n{compose_config}")
            
            # 发送请求到 webhook
            response = requests.post(
                setup_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            # 检查响应
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'success':
                    logger.info(f"Lab 环境 {lab_env.name} 配置成功")
                    return Response({
                        'status': 'success',
                        'message': '环境配置成功',
                        'detail': result.get('message', ''),
                        'file': result.get('file', ''),
                        'compose_id': payload['id']
                    })
                else:
                    error_msg = result.get('error', result.get('message', '未知错误'))
                    logger.error(f"Lab 环境 {lab_env.name} 配置失败: {error_msg}")
                    return Response({
                        'status': 'error',
                        'message': '环境配置失败',
                        'error': error_msg
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                logger.error(f"Webhook 请求失败: HTTP {response.status_code}")
                return Response({
                    'status': 'error',
                    'message': f'Webhook 请求失败: HTTP {response.status_code}',
                    'error': response.text
                }, status=status.HTTP_502_BAD_GATEWAY)
                
        except requests.exceptions.Timeout:
            logger.error(f"Webhook 请求超时")
            return Response({
                'status': 'error',
                'message': 'Webhook 请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
            
        except requests.exceptions.RequestException as e:
            logger.exception(f"Webhook 请求异常: {e}")
            return Response({
                'status': 'error',
                'message': f'Webhook 请求失败: {str(e)}'
            }, status=status.HTTP_502_BAD_GATEWAY)
            
        except Exception as e:
            logger.exception(f"生成配置时发生异常: {e}")
            return Response({
                'status': 'error',
                'message': f'生成配置失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)