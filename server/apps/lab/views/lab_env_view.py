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
from apps.lab.utils.webhook_client import WebhookClient


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
    
    # 统一的超时配置
    WEBHOOK_TIMEOUT_SETUP = 60  # setup操作超时时间(秒)
    WEBHOOK_TIMEOUT_OPERATION = 180  # start/stop/restart操作超时时间(秒)
    WEBHOOK_TIMEOUT_STATUS = 30  # 状态查询超时时间(秒)
    
    def list(self, request, *args, **kwargs):
        """
        重写 list 方法,支持 with_status 参数一次性返回环境列表和状态
        
        GET /api/v1/lab/environments/?with_status=true
        """
        # 获取查询参数
        with_status = request.query_params.get('with_status', 'false').lower() == 'true'
        
        # 调用父类方法获取环境列表
        response = super().list(request, *args, **kwargs)
        
        # 如果不需要状态信息,直接返回
        if not with_status or response.status_code != 200:
            return response
        
        try:
            # 获取环境列表数据
            env_list = response.data.get('results', response.data) if isinstance(response.data, dict) else response.data
            
            if not env_list:
                return response
            
            # 构建环境ID列表
            env_ids = [f"lab-env-{env['id']}" for env in env_list]
            
            # 批量查询状态
            webhook_url = WebhookClient.build_url('status')
            if webhook_url:
                status_response = requests.post(
                    webhook_url,
                    json={'ids': env_ids},
                    timeout=self.WEBHOOK_TIMEOUT_STATUS,
                    headers={'Content-Type': 'application/json'}
                )
                
                if status_response.status_code == 200:
                    status_result = status_response.json()
                    
                    if status_result.get('status') == 'success' and status_result.get('data'):
                        # 创建状态映射
                        status_map = {item['id']: item for item in status_result['data']}
                        
                        # 将状态信息合并到环境列表
                        for env in env_list:
                            env_id = f"lab-env-{env['id']}"
                            env['container_status'] = status_map.get(env_id, {})
                else:
                    logger.warning(f"获取状态失败: HTTP {status_response.status_code}")
            else:
                logger.warning("Webhook URL 未配置,跳过状态查询")
                
        except Exception as e:
            logger.exception(f"合并状态信息时出错: {e}")
            # 出错时不影响环境列表返回
        
        return response
    
    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        """启动 Lab 环境"""
        lab_env = self.get_object()
        compose_id = f"lab-env-{lab_env.id}"
        
        # 使用状态转移方法检查和更新状态
        if lab_env.state == 'running':
            return Response(
                {'detail': 'Lab 环境已经在运行中'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if lab_env.state == 'starting':
            return Response(
                {'detail': 'Lab 环境正在启动中,请勿重复操作'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # 使用 LabUtils 启动环境
        # result = LabUtils.start_lab(lab_env.id)
        try:
            # 1. 生成最新的 compose 配置
            compose_config = ComposeGenerator.generate(lab_env)
            
            # 2. Setup - 更新配置文件
            setup_url = WebhookClient.build_url('setup')
            if not setup_url:
                return Response(
                    {'error': '服务器错误，缺少 webhook 配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            setup_payload = {
                'id': compose_id,
                'compose': compose_config
            }
            
            setup_response = requests.post(
                setup_url,
                json=setup_payload,
                timeout=self.WEBHOOK_TIMEOUT_SETUP,
                headers={'Content-Type': 'application/json'}
            )
            
            if setup_response.status_code != 200:
                error_detail = setup_response.text
                return Response({
                    'status': 'error',
                    'message': '配置更新失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            setup_result = setup_response.json()
            if setup_result.get('status') != 'success':
                return Response(setup_result, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"环境 {lab_env.name} 配置更新成功")

            # 通过requests请求webhook接口将已经生成的compose配置启动
            webhook_url = WebhookClient.build_url('start')
            if not webhook_url:
                return Response(
                    {'error': '服务器错误, 缺少对应启动接口'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            payload = {
                "id": f"lab-env-{lab_env.id}"
            }

            # 使用安全的状态转移方法
            try:
                # 重新从数据库刷新状态,防止在setup期间被stop操作改变
                lab_env.refresh_from_db()
                
                # 如果已经不是stopped状态(可能被stop了),则放弃启动
                if lab_env.state not in ['stopped', 'error']:
                    logger.warning(f"环境 {lab_env.name} 状态已变为 {lab_env.state},放弃启动")
                    return Response(
                        {'detail': f'环境状态已变更为 {lab_env.state},启动已取消'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                lab_env.safe_start()
            except Exception as e:
                logger.error(f"状态转移失败: {e}")
                return Response(
                    {'error': f'无法启动环境: {str(e)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            response = requests.post(
                url=webhook_url,
                json=payload,
                timeout=self.WEBHOOK_TIMEOUT_OPERATION,
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()
                logger.info(f"启动请求响应成功,{response.text}")
                if result.get('status') == 'success':
                    # 在标记为running前,再次检查状态是否仍为starting
                    try:
                        lab_env.refresh_from_db()
                        if lab_env.state != 'starting':
                            # 状态已被改变(可能被stop操作),放弃标记为running
                            logger.warning(f"环境 {lab_env.name} 状态已变为 {lab_env.state},虽然启动成功但不标记为running")
                            return Response({
                                'status': 'cancelled',
                                'message': f'启动操作已被取消,当前状态: {lab_env.state}'
                            }, status=status.HTTP_200_OK)
                        lab_env.mark_running()
                    except Exception as e:
                        logger.error(f"标记running状态失败: {e}")
                        return Response({
                            'status': 'error',
                            'message': '启动成功但状态更新失败',
                            'error': str(e)
                        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                    return Response(result)
                else:
                    # 启动失败,回滚到stopped状态
                    try:
                        lab_env.refresh_from_db()
                        if lab_env.state == 'starting':
                            lab_env.mark_stopped()
                    except Exception as rollback_err:
                        logger.error(f"状态回滚失败: {rollback_err}")
                    return Response(result, status=status.HTTP_400_BAD_REQUEST)
            else:
                # 详细记录响应信息
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"启动请求响应失败: HTTP {response.status_code}, 详情: {error_detail}")
                # webhook请求失败,回滚到stopped状态
                try:
                    lab_env.refresh_from_db()
                    if lab_env.state == 'starting':
                        lab_env.mark_stopped()
                except Exception as rollback_err:
                    logger.error(f"状态回滚失败: {rollback_err}")
                return Response({
                    'status': 'error',
                    'message': f'Webhook 请求失败: HTTP {response.status_code}',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
        
        except requests.exceptions.Timeout:
            logger.error(f"Lab 环境 {lab_env.name} 启动超时: webhook 请求超过 {self.WEBHOOK_TIMEOUT_OPERATION} 秒")
            # 超时回滚状态
            try:
                lab_env.refresh_from_db()
                if lab_env.state == 'starting':
                    lab_env.mark_stopped()
            except Exception as rollback_err:
                logger.error(f"状态回滚失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': '启动请求超时,容器可能仍在后台启动中',
                'error': '请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"Lab 环境 {lab_env.name} 启动时 webhook 请求异常: {e}")
            # 请求异常回滚状态
            try:
                lab_env.refresh_from_db()
                if lab_env.state == 'starting':
                    lab_env.mark_stopped()
            except Exception as rollback_err:
                logger.error(f"状态回滚失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': '启动请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        except Exception as e:
            logger.exception(f"启动环境时发生异常: {e}")
            # 其他异常回滚状态
            try:
                lab_env.refresh_from_db()
                if lab_env.state == 'starting':
                    lab_env.mark_stopped()
            except Exception as rollback_err:
                logger.error(f"状态回滚失败: {rollback_err}")
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
            
            # 允许stopping状态下重复调用(幂等性),直接返回成功
            if lab_env.state == 'stopping':
                logger.info(f"环境 {lab_env.name} 已在停止中,直接返回成功")
                return Response(
                    {'status': 'success', 'message': 'Lab 环境正在停止中'}, 
                    status=status.HTTP_200_OK
                )
            
            # 使用 LabUtils 停止环境
            # result = LabUtils.stop_lab(lab_env.id)

            # 获取webhook url
            webhook_url = WebhookClient.build_url('stop')
            payload = {
                'id': f'lab-env-{lab_env.id}'
            }

            if not webhook_url:
                return Response(
                    {'error': '服务器错误, 缺少对应启动接口'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 使用安全的状态转移方法
            try:
                lab_env.safe_stop()
            except Exception as e:
                logger.error(f"状态转移失败: {e}")
                return Response(
                    {'error': f'无法停止环境: {str(e)}'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=self.WEBHOOK_TIMEOUT_OPERATION,
                headers={'Content-Type': 'application/json'}
            )

            # 检查响应
            if response.status_code == 200:
                result = response.json()

                if result.get('status') == 'success':
                    lab_env.mark_stopped()
                    return Response(result)
                else:
                    lab_env.mark_error()
                    return Response(
                        result,
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # 详细记录响应信息
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"Webhook 请求失败: HTTP {response.status_code}, 详情: {error_detail}")
                # webhook请求失败,标记为error状态
                try:
                    lab_env.refresh_from_db()
                    if lab_env.state == 'stopping':
                        lab_env.mark_error()
                except Exception as rollback_err:
                    logger.error(f"状态更新失败: {rollback_err}")
                return Response({
                    'status': 'error',
                    'message': f'Webhook 请求失败: HTTP {response.status_code}',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
        except requests.exceptions.Timeout:
            logger.error(f"Lab 环境 {lab_env.name} 停止超时: webhook 请求超过 {self.WEBHOOK_TIMEOUT_OPERATION} 秒")
            lab_env.mark_error()
            return Response({
                'status': 'error',
                'message': f'停止请求超时(超过{self.WEBHOOK_TIMEOUT_OPERATION}秒)，请检查容器状态或重试',
                'error': '请求超时'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"Lab 环境 {lab_env.name} 停止时 webhook 请求异常: {e}")
            # 请求异常标记为error状态
            try:
                lab_env.refresh_from_db()
                if lab_env.state == 'stopping':
                    lab_env.mark_error()
            except Exception as rollback_err:
                logger.error(f"状态更新失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': '停止请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
            
        except Exception as e:
            logger.exception(f"停止Lab 容器错误: {e}")
            # 其他异常标记为error状态
            try:
                lab_env.refresh_from_db()
                if lab_env.state == 'stopping':
                    lab_env.mark_error()
            except Exception as rollback_err:
                logger.error(f"状态更新失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': '停止失败',
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        
    @action(detail=True, methods=['post'])
    def restart(self, request, pk=None):
        """更新并重启 Lab 环境（使用 setup + stop + start 组合实现）"""
        lab_env = self.get_object()
        compose_id = f"lab-env-{lab_env.id}"
        try:
            # 1. 生成最新的 compose 配置
            compose_config = ComposeGenerator.generate(lab_env)
            
            # 2. Setup - 更新配置文件
            setup_url = WebhookClient.build_url('setup')
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
                timeout=self.WEBHOOK_TIMEOUT_SETUP,
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
            stop_url = WebhookClient.build_url('stop')
            stop_payload = {'id': compose_id}
            
            logger.info(f"正在停止环境 {lab_env.name}")
            stop_response = requests.post(
                stop_url,
                json=stop_payload,
                timeout=self.WEBHOOK_TIMEOUT_OPERATION,
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
            start_url = WebhookClient.build_url('start')
            start_payload = {'id': compose_id}
            
            logger.info(f"正在启动环境 {lab_env.name}")
            start_response = requests.post(
                start_url,
                json=start_payload,
                timeout=self.WEBHOOK_TIMEOUT_OPERATION,
                headers={'Content-Type': 'application/json'}
            )
            
            if start_response.status_code != 200:
                error_detail = start_response.text
                logger.error(f"启动失败: {error_detail}")
                try:
                    lab_env.refresh_from_db()
                    if lab_env.state not in ['error', 'stopped']:
                        lab_env.mark_error()
                except Exception as rollback_err:
                    logger.error(f"状态更新失败: {rollback_err}")
                return Response({
                    'status': 'error',
                    'message': '启动失败',
                    'error': error_detail
                }, status=status.HTTP_502_BAD_GATEWAY)
            
            start_result = start_response.json()
            if start_result.get('status') == 'success':
                logger.info(f"环境 {lab_env.name} 重启成功")
                # 在标记为running前,检查当前状态
                try:
                    lab_env.refresh_from_db()
                    if lab_env.state != 'running':
                        lab_env.mark_running()
                    else:
                        logger.info(f"环境 {lab_env.name} 已经是running状态,跳过状态更新")
                except Exception as e:
                    logger.error(f"更新状态失败: {e}")
                    # 即使状态更新失败,重启操作本身已成功,返回成功
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
                try:
                    lab_env.refresh_from_db()
                    if lab_env.state not in ['error', 'stopped']:
                        lab_env.mark_error()
                except Exception as rollback_err:
                    logger.error(f"状态更新失败: {rollback_err}")
                return Response(start_result, status=status.HTTP_400_BAD_REQUEST)
        
        except requests.exceptions.Timeout:
            logger.error(f"环境 {lab_env.name} 重启超时: 请求超过 {self.WEBHOOK_TIMEOUT_OPERATION} 秒")
            try:
                lab_env.refresh_from_db()
                if lab_env.state not in ['error', 'stopped']:
                    lab_env.mark_error()
            except Exception as rollback_err:
                logger.error(f"状态更新失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': f'重启请求超时(超过{self.WEBHOOK_TIMEOUT_OPERATION}秒)，请检查容器状态或重试'
            }, status=status.HTTP_504_GATEWAY_TIMEOUT)
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"环境 {lab_env.name} 重启时网络异常: {e}")
            try:
                lab_env.refresh_from_db()
                if lab_env.state not in ['error', 'stopped']:
                    lab_env.mark_error()
            except Exception as rollback_err:
                logger.error(f"状态更新失败: {rollback_err}")
            return Response({
                'status': 'error',
                'message': '重启请求失败',
                'error': str(e)
            }, status=status.HTTP_502_BAD_GATEWAY)
        
        except Exception as e:
            logger.exception(f"重启 Lab 环境异常: {e}")
            try:
                lab_env.refresh_from_db()
                if lab_env.state not in ['error', 'stopped']:
                    lab_env.mark_error()
            except Exception as rollback_err:
                logger.error(f"状态更新失败: {rollback_err}")
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
            
            webhook_url = WebhookClient.build_url('status')
            if not webhook_url:
                return Response({
                    'error': '服务器错误，缺少 webhook 配置'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 单个查询
            payload = {'id': f"lab-env-{lab_env.id}"}
            
            # 发送请求到 webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=self.WEBHOOK_TIMEOUT_STATUS,
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
            
            # 单个查询：更新单个环境状态
            if result.get('status') == 'success':
                containers = result.get('containers', [])
                if not containers:
                    logger.info(f"stop")
                    lab_env.state = 'stopped'
                elif all(c.get('State') == 'running' for c in containers):
                    logger.info(f"run")
                    lab_env.state = 'running'
                elif any(c.get('State') in ['exited', 'dead'] for c in containers):
                    logger.info('exit')
                    lab_env.state = 'stopped'
                else:
                    logger.info(f"error")
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
            webhook_url = WebhookClient.build_url('status')
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
            
            # 发送请求到 webhook
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=self.WEBHOOK_TIMEOUT_STATUS,
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
                            if not containers:
                                env.state = 'stopped'
                            elif all(c.get('State') == 'running' for c in containers):
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
            webhook_url = WebhookClient.build_url('setup')
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
                timeout=self.WEBHOOK_TIMEOUT_SETUP,
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