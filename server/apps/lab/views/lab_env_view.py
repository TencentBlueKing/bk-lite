# -*- coding: utf-8 -*-
"""
Lab 环境视图
"""

import os
import requests
from rest_framework import status
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
        # result = LabUtils.start_lab(lab_env.id)
        try:
            # 通过requests请求webhook接口将已经生成的compose配置启动
            webhook_url = self.get_webhook_url('start')
            if not webhook_url:
                return Response(
                    {'error': '服务器错误, 缺少对应启动接口'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            payload = {
                "id": f"lab-env-{lab_env.id}"
            }

            lab_env.state = 'starting'
            lab_env.save(update_fields=['state', 'updated_at'])
            response = requests.post(
                url=webhook_url,
                json=payload,
                timeout=120,  # 增加超时时间到 120 秒，容器启动可能需要较长时间
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    lab_env.state = 'running'
                    lab_env.save(update_fields=['state', 'updated_at'])
                    return Response(result)
                else:
                    lab_env.state = 'error'
                    lab_env.save(update_fields=['state', 'updated_at'])
                    return Response(result, status=status.HTTP_400_BAD_REQUEST)
            else:
                # 详细记录响应信息
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"Webhook 请求失败: HTTP {response.status_code}, 详情: {error_detail}")
                return Response({
                    'status': 'error',
                    'message': f'Webhook 请求失败: HTTP {response.status_code}',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
        
        except requests.exceptions.Timeout:
            logger.error(f"Lab 环境 {lab_env.name} 启动超时: webhook 请求超过 120 秒")
            return Response({
                'status': 'error',
                'message': '启动请求超时，容器可能仍在后台启动中',
                'error': '请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"Lab 环境 {lab_env.name} 启动时 webhook 请求异常: {e}")
            return Response({
                'status': 'error',
                'message': '启动请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        except Exception as e:
            logger.exception(f"启动环境时发生异常: {e}")
            return Response({
                'status': 'error',
                'message': '启动失败',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
    @action(detail=True, methods=['post'])
    def stop(self, request, pk=None):
        """停止 Lab 环境"""
        try:
            lab_env = self.get_object()

            if lab_env.state == 'stopped':
                return Response(
                    {'detail': 'Lab 环境已经停止'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 使用 LabUtils 停止环境
            # result = LabUtils.stop_lab(lab_env.id)

            # 获取webhook url
            webhook_url = self.get_webhook_url('stop')
            payload = {
                'id': f'lab-env-{lab_env.id}'
            }

            if not webhook_url:
                return Response(
                    {'error': '服务器错误, 缺少对应启动接口'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            lab_env.state = 'stopping'
            lab_env.save(update_fields=['state', 'updated_at'])
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=120,
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()

                if result.get('status') == 'success':
                    lab_env.state = 'stopped'
                    lab_env.save(update_fields=['state', 'updated_at'])
                    return Response(result)
                else:
                    lab_env.state = 'error'
                    lab_env.save(update_fields=['state', 'updated_at'])
                    return Response(
                        result,
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # 详细记录响应信息
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"Webhook 请求失败: HTTP {response.status_code}, 详情: {error_detail}")
                return Response({
                    'status': 'error',
                    'message': f'Webhook 请求失败: HTTP {response.status_code}',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
        except requests.exceptions.Timeout:
            logger.error(f"Lab 环境 {lab_env.name} 启动超时: webhook 请求超过 120 秒")
            return Response({
                'status': 'error',
                'message': '启动请求超时，容器可能仍在后台启动中',
                'error': '请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"Lab 环境 {lab_env.name} 启动时 webhook 请求异常: {e}")
            return Response({
                'status': 'error',
                'message': '启动请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
            
        except Exception as e:
            logger.error(f"停止Lab 容器错误: {e}")
            return Response(
                {'error': f'停止lab-env-{lab_env.id}容器错误'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """更新并重启 Lab 环境（使用 setup + stop + start 组合实现）"""
        lab_env = self.get_object()
        compose_id = f"lab-env-{lab_env.id}"
        
        try:
            # 1. 生成最新的 compose 配置
            compose_config = ComposeGenerator.generate(lab_env)
            
            # 2. Setup - 更新配置文件
            setup_url = self.get_webhook_url('setup')
            if not setup_url:
                return Response(
                    {'error': '服务器错误，缺少 webhook 配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            setup_payload = {
                'id': compose_id,
                'compose': compose_config
            }
            
            logger.info(f"正在更新环境 {lab_env.name} 的配置")
            setup_response = requests.post(
                setup_url,
                json=setup_payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            if setup_response.status_code != 200:
                error_detail = setup_response.text
                logger.error(f"配置更新失败: {error_detail}")
                return Response({
                    'status': 'error',
                    'message': '配置更新失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            setup_result = setup_response.json()
            if setup_result.get('status') != 'success':
                logger.error(f"配置验证失败: {setup_result.get('error', '未知错误')}")
                return Response(setup_result, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"环境 {lab_env.name} 配置更新成功")
            
            # 3. Stop - 停止现有容器
            stop_url = self.get_webhook_url('stop')
            stop_payload = {'id': compose_id}
            
            logger.info(f"正在停止环境 {lab_env.name}")
            stop_response = requests.post(
                stop_url,
                json=stop_payload,
                timeout=60,
                headers={'Content-Type': 'application/json'}
            )
            
            # 容器可能不存在（首次启动），忽略停止失败
            if stop_response.status_code == 200:
                stop_result = stop_response.json()
                if stop_result.get('status') == 'success':
                    logger.info(f"环境 {lab_env.name} 已停止")
                else:
                    logger.warning(f"停止环境时出现警告: {stop_result.get('message', '')}")
            else:
                logger.warning(f"停止操作失败（可能容器不存在）: {stop_response.text}")
            
            # 4. Start - 启动容器
            start_url = self.get_webhook_url('start')
            start_payload = {'id': compose_id}
            
            logger.info(f"正在启动环境 {lab_env.name}")
            start_response = requests.post(
                start_url,
                json=start_payload,
                timeout=120,
                headers={'Content-Type': 'application/json'}
            )
            
            if start_response.status_code != 200:
                error_detail = start_response.text
                logger.error(f"启动失败: {error_detail}")
                lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
                return Response({
                    'status': 'error',
                    'message': '启动失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            start_result = start_response.json()
            if start_result.get('status') == 'success':
                logger.info(f"环境 {lab_env.name} 重启成功")
                lab_env.state = 'running'
                lab_env.save(update_fields=['state', 'updated_at'])
                return Response({
                    'status': 'success',
                    'message': '环境已成功重启',
                    'details': {
                        'setup': setup_result.get('message', ''),
                        'start': start_result.get('message', '')
                    }
                })
            else:
                logger.error(f"启动失败: {start_result.get('error', '未知错误')}")
                lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
                return Response(start_result, status=status.HTTP_400_BAD_REQUEST)
        
        except requests.exceptions.Timeout:
            logger.error(f"环境 {lab_env.name} 重启超时")
            lab_env.state = 'error'
            lab_env.save(update_fields=['state', 'updated_at'])
            return Response({
                'status': 'error',
                'message': '重启请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"环境 {lab_env.name} 重启时网络异常: {e}")
            lab_env.state = 'error'
            lab_env.save(update_fields=['state', 'updated_at'])
            return Response({
                'status': 'error',
                'message': '重启请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        except Exception as e:
            logger.exception(f"重启 Lab 环境异常: {e}")
            lab_env.state = 'error'
            lab_env.save(update_fields=['state', 'updated_at'])
            return Response({
                'status': 'error',
                'message': '重启失败',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        
    @action(detail=True, methods=['get'], url_path='status')
    def status(self, request, pk=None):
        """
        获取单个环境状态
        GET /api/v1/lab/environments/{id}/status/ - 获取单个环境状态
        """
        try:
            lab_env = self.get_object()
            
            webhook_url = self.get_webhook_url('status')
            if not webhook_url:
                return Response({
                    'error': '服务器错误，缺少 webhook 配置'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 单个查询
            payload = {'id': f"lab-env-{lab_env.id}"}
            logger.info(f"查询环境 {lab_env.name} (ID: {lab_env.id}) 的状态")
            
            # 发送请求到 webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"获取状态失败: HTTP {response.status_code}, {error_detail}")
                return Response({
                    'status': 'error',
                    'message': '获取状态失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            # 记录响应信息用于调试
            logger.info(f"response status: {response.status_code}, content-type: {response.headers.get('content-type')}")
            logger.info(f"response length: {len(response.text)} bytes")
            logger.info(f"response first 200 chars: {response.text[:200]}")
            logger.info(f"response last 200 chars: {response.text[-200:]}")
            
            # 解析 JSON
            try:
                result = response.json()
            except ValueError as e:
                logger.error(f"JSON 解析失败: {e}")
                raise
            
            # 单个查询：更新单个环境状态
            if result.get('status') == 'success':
                containers = result.get('containers', [])
                if containers and all(c.get('State') == 'running' for c in containers):
                    lab_env.state = 'running'
                elif any(c.get('State') in ['exited', 'dead'] for c in containers):
                    lab_env.state = 'stopped'
                else:
                    lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
            
            return Response(result)

        except Exception as e:
            logger.exception(f"获取环境状态错误: {e}")
            return Response({
                'status': 'error',
                'message': '获取环境状态失败',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['get'], url_path='status')
    def status_batch(self, request):
        """
        批量获取所有环境状态
        GET /api/v1/lab/environments/status/ - 获取所有环境状态
        """
        try:
            webhook_url = self.get_webhook_url('status')
            if not webhook_url:
                return Response({
                    'error': '服务器错误，缺少 webhook 配置'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 批量查询所有环境
            lab_envs = self.get_queryset()
            env_ids = [f"lab-env-{env.id}" for env in lab_envs]
            
            if not env_ids:
                return Response({
                    'status': 'success',
                    'data': [],
                    'message': '没有可用的环境'
                })
            
            payload = {'ids': env_ids}
            logger.info(f"批量查询 {len(env_ids)} 个环境的状态")
            
            # 发送请求到 webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(f"获取状态失败: HTTP {response.status_code}, {error_detail}")
                return Response({
                    'status': 'error',
                    'message': '获取状态失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            # 解析 JSON
            try:
                result = response.json()
            except ValueError as e:
                logger.error(f"JSON 解析失败: {e}")
                raise
            
            # 批量查询：更新所有环境状态
            if result.get('status') == 'success' and result.get('data'):
                env_map = {env.id: env for env in lab_envs}
                
                for item in result['data']:
                    env_id_str = item.get('id', '')
                    if env_id_str.startswith('lab-env-'):
                        env_id = int(env_id_str.replace('lab-env-', ''))
                        env = env_map.get(env_id)
                        
                        if env and item.get('status') == 'success':
                            containers = item.get('containers', [])
                            if containers and all(c.get('State') == 'running' for c in containers):
                                env.state = 'running'
                            elif any(c.get('State') in ['exited', 'dead'] for c in containers):
                                env.state = 'stopped'
                            else:
                                env.state = 'error'
                            env.save(update_fields=['state', 'updated_at'])
            
            return Response(result)

        except Exception as e:
            logger.exception(f"批量获取环境状态错误: {e}")
            return Response({
                'status': 'error',
                'message': '批量获取环境状态失败',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
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
            
            # 获取 webhook URL
            webhook_url = self.get_webhook_url('setup')
            if not webhook_url:
                return Response(
                    {'error': '服务器错误, 缺少对应启动接口'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                      
            # 准备请求数据
            payload = {
                "id": f"lab-env-{lab_env.id}",
                "compose": compose_config
            }
            
            logger.info(f"正在配置 Lab 环境 {lab_env.name} (ID: {lab_env.id})")
            logger.debug(f"Docker Compose 配置:\n{compose_config}")
            
            # 发送请求到 webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30,
                headers={'Content-Type': 'application/json'}
            )
            
            # 检查响应
            if response.status_code == 200:
                result = response.json()
                
                if result.get('status') == 'success':
                    return Response(result)
                else:
                    return Response(result, status=status.HTTP_400_BAD_REQUEST)
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
        
    def get_webhook_url(self, name):
        webhook_base_url = os.getenv('WEBHOOK', None)

        if not webhook_base_url:
            return None
        
        if not webhook_base_url.endswith('/'):
            webhook_base_url += '/'
        
        return f"{webhook_base_url}{name}"