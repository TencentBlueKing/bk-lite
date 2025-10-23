# -*- coding: utf-8 -*-
"""
Lab 环境管理工具类
参考 OpsPilot 的实现模式，支持 Docker 和 Kubernetes 两种运行时
"""

import os
from typing import Dict, Any, List, Optional

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.config import LAB_RUNTIME
from apps.lab.utils.docker_lab_client import DockerLabClient
from apps.lab.utils.kubernetes_lab_client import KubernetesLabClient


class LabUtils:
    """Lab 环境管理工具类"""
    
    _client = None
    
    @classmethod
    def _get_client(cls):
        """获取运行时客户端（单例模式）"""
        if cls._client is None:
            if LAB_RUNTIME.lower() == "docker":
                logger.info("使用 Docker 运行时管理 Lab 环境")
                cls._client = DockerLabClient()
            else:
                logger.info("使用 Kubernetes 运行时管理 Lab 环境")
                cls._client = KubernetesLabClient()
        return cls._client
    
    @classmethod
    def start_lab(cls, lab_id: int) -> Dict[str, Any]:
        """
        启动 Lab 环境
        
        Args:
            lab_id: Lab 环境 ID
            
        Returns:
            操作结果字典
        """
        try:
            from apps.lab.models import LabEnv
            lab_env = LabEnv.objects.get(id=lab_id)
            
            if lab_env.state == 'running':
                return {'success': False, 'message': 'Lab 环境已经在运行中'}
            
            # 更新状态为启动中
            lab_env.state = 'starting'
            lab_env.save(update_fields=['state', 'updated_at'])
            
            # 使用运行时客户端启动环境
            client = cls._get_client()
            result = client.start_lab_env(lab_env)
            
            if result.get('success'):
                lab_env.state = 'running'
                lab_env.endpoint = result.get('endpoint')
                lab_env.save(update_fields=['state', 'endpoint', 'updated_at'])
                logger.info(f"Lab 环境 {lab_id} 启动成功")
            else:
                lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
                logger.error(f"Lab 环境 {lab_id} 启动失败: {result.get('message')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"启动 Lab 环境 {lab_id} 异常: {e}")
            try:
                lab_env = LabEnv.objects.get(id=lab_id)
                lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
            except:
                pass
            return {'success': False, 'message': f'启动失败: {str(e)}'}
    
    @classmethod
    def stop_lab(cls, lab_id: int) -> Dict[str, Any]:
        """
        停止 Lab 环境
        
        Args:
            lab_id: Lab 环境 ID
            
        Returns:
            操作结果字典
        """
        try:
            from apps.lab.models import LabEnv
            lab_env = LabEnv.objects.get(id=lab_id)
            
            if lab_env.state == 'stopped':
                return {'success': False, 'message': 'Lab 环境已经停止'}
            
            # 更新状态为停止中
            lab_env.state = 'stopping'
            lab_env.save(update_fields=['state', 'updated_at'])
            
            # 使用运行时客户端停止环境
            client = cls._get_client()
            result = client.stop_lab_env(lab_env)
            
            if result.get('success'):
                lab_env.state = 'stopped'
                lab_env.endpoint = None
                lab_env.save(update_fields=['state', 'endpoint', 'updated_at'])
                logger.info(f"Lab 环境 {lab_id} 停止成功")
            else:
                lab_env.state = 'error'
                lab_env.save(update_fields=['state', 'updated_at'])
                logger.error(f"Lab 环境 {lab_id} 停止失败: {result.get('message')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"停止 Lab 环境 {lab_id} 异常: {e}")
            return {'success': False, 'message': f'停止失败: {str(e)}'}
    
    @classmethod
    def get_lab_status(cls, lab_id: int) -> Dict[str, Any]:
        """
        获取 Lab 环境状态
        
        Args:
            lab_id: Lab 环境 ID
            
        Returns:
            状态信息字典
        """
        try:
            from apps.lab.models import LabEnv
            lab_env = LabEnv.objects.select_related('ide_image').prefetch_related('infra_instances__image').get(id=lab_id)
            
            # 使用运行时客户端获取实时状态
            client = cls._get_client()
            runtime_status = client.get_lab_env_status(lab_env)
            
            # 基础设施实例状态
            infra_status = []
            for instance in lab_env.infra_instances.all():
                instance_status = client.get_infra_instance_status(instance)
                infra_status.append({
                    'id': instance.id,
                    'name': instance.name,
                    'image_name': instance.image.name,
                    'image_version': instance.image.version,
                    'status': instance.status,
                    'status_display': instance.get_status_display(),
                    'endpoint': instance.endpoint,
                    'runtime_status': instance_status
                })
            
            return {
                'id': lab_env.id,
                'name': lab_env.name,
                'state': lab_env.state,
                'state_display': lab_env.get_state_display(),
                'endpoint': lab_env.endpoint,
                'ide_image': {
                    'name': lab_env.ide_image.name,
                    'version': lab_env.ide_image.version,
                },
                'infra_instances': infra_status,
                'resources': {
                    'cpu': lab_env.cpu,
                    'memory': lab_env.memory,
                    'gpu': lab_env.gpu,
                    'volume_size': lab_env.volume_size,
                },
                'runtime_status': runtime_status,
                'created_at': lab_env.created_at,
                'updated_at': lab_env.updated_at,
            }
            
        except Exception as e:
            logger.exception(f"获取 Lab 环境 {lab_id} 状态异常: {e}")
            return {'error': f'获取状态失败: {str(e)}'}
    
    @classmethod
    def list_running_labs(cls) -> List[Dict[str, Any]]:
        """
        列出所有运行中的 Lab 环境
        
        Returns:
            运行中的 Lab 环境列表
        """
        try:
            client = cls._get_client()
            return client.list_running_lab_envs()
        except Exception as e:
            logger.exception(f"列出运行中的 Lab 环境异常: {e}")
            return []
    
    @classmethod
    def cleanup_orphaned_resources(cls) -> Dict[str, Any]:
        """
        清理孤儿资源（没有对应数据库记录的容器/Pod）
        
        Returns:
            清理结果
        """
        try:
            client = cls._get_client()
            return client.cleanup_orphaned_resources()
        except Exception as e:
            logger.exception(f"清理孤儿资源异常: {e}")
            return {'success': False, 'message': f'清理失败: {str(e)}'}