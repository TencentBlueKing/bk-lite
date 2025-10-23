# -*- coding: utf-8 -*-
"""
Docker Lab 客户端
基于 Docker 运行时管理 Lab 环境
"""

import docker
from typing import Dict, Any, List, Optional

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.config import CONVERSATION_DOCKER_NETWORK


class DockerLabClient:
    """Docker Lab 环境管理客户端"""
    
    def __init__(self):
        """初始化 Docker 客户端"""
        try:
            self.client = docker.from_env()
            self.api_client = docker.APIClient()
            logger.info("Docker Lab 客户端初始化成功")
        except Exception as e:
            logger.error(f"Docker Lab 客户端初始化失败: {e}")
            raise Exception("无法连接到 Docker 服务，请检查 Docker 是否正常运行")
    
    def start_lab_env(self, lab_env) -> Dict[str, Any]:
        """
        启动 Lab 环境
        
        流程：
        1. 创建专用网络
        2. 启动基础设施实例容器
        3. 启动 IDE 容器
        4. 配置网络连接
        """
        try:
            lab_id = lab_env.id
            network_name = f"lab-network-{lab_id}"
            
            # 1. 创建专用网络
            network = self._create_lab_network(network_name)
            
            # 2. 启动基础设施实例
            infra_endpoints = []
            for instance in lab_env.infra_instances.all():
                result = self._start_infra_instance(instance, network_name)
                if result.get('success'):
                    infra_endpoints.append(result.get('endpoint'))
                else:
                    logger.error(f"启动基础设施实例 {instance.name} 失败")
            
            # 3. 启动 IDE 容器
            ide_result = self._start_ide_container(lab_env, network_name, infra_endpoints)
            
            if ide_result.get('success'):
                return {
                    'success': True,
                    'endpoint': ide_result.get('endpoint'),
                    'message': f'Lab 环境 {lab_id} 启动成功'
                }
            else:
                # 清理已启动的资源
                self._cleanup_lab_resources(lab_id)
                return {
                    'success': False,
                    'message': f'启动 IDE 容器失败: {ide_result.get("message")}'
                }
                
        except Exception as e:
            logger.exception(f"启动 Lab 环境 {lab_env.id} 异常: {e}")
            self._cleanup_lab_resources(lab_env.id)
            return {'success': False, 'message': f'启动异常: {str(e)}'}
    
    def stop_lab_env(self, lab_env) -> Dict[str, Any]:
        """停止 Lab 环境"""
        try:
            lab_id = lab_env.id
            
            # 停止 IDE 容器
            self._stop_container(f"lab-ide-{lab_id}")
            
            # 停止基础设施实例容器
            for instance in lab_env.infra_instances.all():
                self._stop_container(f"lab-infra-{instance.id}")
            
            # 删除网络
            self._remove_lab_network(f"lab-network-{lab_id}")
            
            return {'success': True, 'message': f'Lab 环境 {lab_id} 停止成功'}
            
        except Exception as e:
            logger.exception(f"停止 Lab 环境 {lab_env.id} 异常: {e}")
            return {'success': False, 'message': f'停止异常: {str(e)}'}
    
    def get_lab_env_status(self, lab_env) -> Dict[str, Any]:
        """获取 Lab 环境运行时状态"""
        try:
            lab_id = lab_env.id
            ide_container_name = f"lab-ide-{lab_id}"
            
            # 检查 IDE 容器状态
            ide_status = self._get_container_status(ide_container_name)
            
            # 检查基础设施实例状态
            infra_statuses = []
            for instance in lab_env.infra_instances.all():
                container_name = f"lab-infra-{instance.id}"
                status = self._get_container_status(container_name)
                infra_statuses.append({
                    'instance_id': instance.id,
                    'container_name': container_name,
                    'status': status
                })
            
            return {
                'runtime': 'docker',
                'ide_container': {
                    'name': ide_container_name,
                    'status': ide_status
                },
                'infra_containers': infra_statuses,
                'network': f"lab-network-{lab_id}"
            }
            
        except Exception as e:
            logger.exception(f"获取 Lab 环境 {lab_env.id} 运行时状态异常: {e}")
            return {'error': str(e)}
    
    def get_infra_instance_status(self, instance) -> Dict[str, Any]:
        """获取基础设施实例运行时状态"""
        try:
            container_name = f"lab-infra-{instance.id}"
            status = self._get_container_status(container_name)
            return {
                'container_name': container_name,
                'status': status
            }
        except Exception as e:
            logger.exception(f"获取基础设施实例 {instance.id} 状态异常: {e}")
            return {'error': str(e)}
    
    def list_running_lab_envs(self) -> List[Dict[str, Any]]:
        """列出所有运行中的 Lab 环境"""
        try:
            containers = self.client.containers.list(filters={'label': 'app=lab-env'})
            lab_envs = []
            
            for container in containers:
                labels = container.labels
                if 'lab-id' in labels:
                    lab_envs.append({
                        'lab_id': labels['lab-id'],
                        'container_name': container.name,
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else 'unknown'
                    })
            
            return lab_envs
            
        except Exception as e:
            logger.exception(f"列出运行中的 Lab 环境异常: {e}")
            return []
    
    def cleanup_orphaned_resources(self) -> Dict[str, Any]:
        """清理孤儿资源"""
        try:
            # 获取所有 lab 相关的容器
            containers = self.client.containers.list(all=True, filters={'label': 'app=lab-env'})
            
            # 获取数据库中的有效 lab_id
            from apps.lab.models import LabEnv
            valid_lab_ids = set(str(lab.id) for lab in LabEnv.objects.all())
            
            cleaned_containers = []
            for container in containers:
                lab_id = container.labels.get('lab-id')
                if lab_id and lab_id not in valid_lab_ids:
                    container.remove(force=True)
                    cleaned_containers.append(container.name)
                    logger.info(f"清理孤儿容器: {container.name}")
            
            # 清理孤儿网络
            networks = self.client.networks.list(filters={'label': 'app=lab-env'})
            cleaned_networks = []
            for network in networks:
                lab_id = network.labels.get('lab-id')
                if lab_id and lab_id not in valid_lab_ids:
                    network.remove()
                    cleaned_networks.append(network.name)
                    logger.info(f"清理孤儿网络: {network.name}")
            
            return {
                'success': True,
                'cleaned_containers': cleaned_containers,
                'cleaned_networks': cleaned_networks
            }
            
        except Exception as e:
            logger.exception(f"清理孤儿资源异常: {e}")
            return {'success': False, 'message': str(e)}
    
    def _create_lab_network(self, network_name: str):
        """创建 Lab 专用网络"""
        try:
            # 检查网络是否已存在
            try:
                existing_network = self.client.networks.get(network_name)
                logger.info(f"网络 {network_name} 已存在，复用现有网络")
                return existing_network
            except docker.errors.NotFound:
                pass
            
            # 创建新网络
            network = self.client.networks.create(
                name=network_name,
                driver="bridge",
                labels={
                    'app': 'lab-env',
                    'lab-id': network_name.replace('lab-network-', '')
                }
            )
            logger.info(f"创建网络 {network_name} 成功")
            return network
            
        except Exception as e:
            logger.error(f"创建网络 {network_name} 失败: {e}")
            raise
    
    def _start_infra_instance(self, instance, network_name: str) -> Dict[str, Any]:
        """启动基础设施实例容器"""
        try:
            container_name = f"lab-infra-{instance.id}"
            
            # 清理可能存在的同名容器
            self._remove_container_if_exists(container_name)
            
            # 构建环境变量
            environment = {
                'TZ': 'Asia/Shanghai',
                **instance.env_vars  # 使用实例配置的环境变量
            }
            
            # 端口映射
            ports = {}
            for container_port, host_port in instance.port_mappings.items():
                ports[f"{container_port}/tcp"] = host_port
            
            # 卷挂载
            volumes = {}
            for mount in instance.volume_mounts:
                volumes[mount['host_path']] = {
                    'bind': mount['container_path'],
                    'mode': 'ro' if mount.get('read_only', False) else 'rw'
                }
            
            # 资源限制
            mem_limit = instance.memory_limit if instance.memory_limit else None
            cpu_quota = None
            if instance.cpu_limit:
                cpu_quota = int(float(instance.cpu_limit) * 100000)  # Docker CPU quota
            
            # 启动容器
            container = self.client.containers.run(
                image=f"{instance.image.name}:{instance.image.version}",
                name=container_name,
                detach=True,
                environment=environment,
                ports=ports,
                volumes=volumes,
                network=network_name,
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                command=instance.command if instance.command else None,
                labels={
                    'app': 'lab-env',
                    'component': 'infra',
                    'instance-id': str(instance.id),
                    'lab-id': str(instance.lab_envs.first().id) if instance.lab_envs.exists() else ''
                },
                restart_policy={'Name': 'always'}
            )
            
            # 更新实例状态
            instance.status = 'running'
            instance.save(update_fields=['status', 'updated_at'])
            
            logger.info(f"启动基础设施实例容器 {container_name} 成功")
            return {
                'success': True,
                'container_id': container.id,
                'endpoint': f"http://{container_name}:8080"  # 假设默认端口
            }
            
        except Exception as e:
            logger.error(f"启动基础设施实例 {instance.id} 失败: {e}")
            instance.status = 'error'
            instance.save(update_fields=['status', 'updated_at'])
            return {'success': False, 'message': str(e)}
    
    def _start_ide_container(self, lab_env, network_name: str, infra_endpoints: List[str]) -> Dict[str, Any]:
        """启动 IDE 容器"""
        try:
            container_name = f"lab-ide-{lab_env.id}"
            
            # 清理可能存在的同名容器
            self._remove_container_if_exists(container_name)
            
            # 构建环境变量
            environment = {
                'TZ': 'Asia/Shanghai',
                'LAB_ENV_ID': str(lab_env.id),
                'LAB_ENV_NAME': lab_env.name,
                'INFRA_ENDPOINTS': ','.join(infra_endpoints),
            }
            
            # 端口映射（IDE 通常使用固定端口，如 8888 for Jupyter）
            ports = {'8888/tcp': None}  # 随机分配主机端口
            
            # 持久化存储
            volumes = {
                f"lab-storage-{lab_env.id}": {
                    'bind': '/workspace',
                    'mode': 'rw'
                }
            }
            
            # 资源限制
            mem_limit = lab_env.memory
            cpu_quota = int(lab_env.cpu * 100000)  # Docker CPU quota
            
            # GPU 支持
            device_requests = []
            if lab_env.gpu > 0:
                device_requests = [
                    docker.types.DeviceRequest(count=lab_env.gpu, capabilities=[['gpu']])
                ]
            
            # 启动容器
            container = self.client.containers.run(
                image=f"{lab_env.ide_image.name}:{lab_env.ide_image.version}",
                name=container_name,
                detach=True,
                environment=environment,
                ports=ports,
                volumes=volumes,
                network=network_name,
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                device_requests=device_requests,
                labels={
                    'app': 'lab-env',
                    'component': 'ide',
                    'lab-id': str(lab_env.id)
                },
                restart_policy={'Name': 'always'}
            )
            
            # 获取分配的端口
            container.reload()
            port_info = container.ports.get('8888/tcp')
            host_port = port_info[0]['HostPort'] if port_info else '8888'
            endpoint = f"http://localhost:{host_port}"
            
            logger.info(f"启动 IDE 容器 {container_name} 成功，访问地址: {endpoint}")
            return {
                'success': True,
                'container_id': container.id,
                'endpoint': endpoint
            }
            
        except Exception as e:
            logger.error(f"启动 IDE 容器失败: {e}")
            return {'success': False, 'message': str(e)}
    
    def _stop_container(self, container_name: str):
        """停止并删除容器"""
        try:
            try:
                container = self.client.containers.get(container_name)
                if container.status == 'running':
                    container.stop(timeout=10)
                    logger.info(f"停止容器 {container_name} 成功")
                container.remove()
                logger.info(f"删除容器 {container_name} 成功")
            except docker.errors.NotFound:
                logger.info(f"容器 {container_name} 不存在，跳过删除")
        except Exception as e:
            logger.error(f"停止容器 {container_name} 失败: {e}")
    
    def _remove_lab_network(self, network_name: str):
        """删除 Lab 网络"""
        try:
            try:
                network = self.client.networks.get(network_name)
                network.remove()
                logger.info(f"删除网络 {network_name} 成功")
            except docker.errors.NotFound:
                logger.info(f"网络 {network_name} 不存在，跳过删除")
        except Exception as e:
            logger.error(f"删除网络 {network_name} 失败: {e}")
    
    def _get_container_status(self, container_name: str) -> Dict[str, Any]:
        """获取容器状态"""
        try:
            container = self.client.containers.get(container_name)
            return {
                'status': container.status,
                'health': container.attrs.get('State', {}).get('Health', {}).get('Status'),
                'created': container.attrs.get('Created'),
                'started': container.attrs.get('State', {}).get('StartedAt')
            }
        except docker.errors.NotFound:
            return {'status': 'not_found'}
        except Exception as e:
            logger.error(f"获取容器 {container_name} 状态失败: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _remove_container_if_exists(self, container_name: str):
        """如果容器存在则删除"""
        try:
            container = self.client.containers.get(container_name)
            if container.status == 'running':
                container.stop(timeout=10)
            container.remove(force=True)
            logger.info(f"删除已存在的容器 {container_name}")
        except docker.errors.NotFound:
            pass
        except Exception as e:
            logger.error(f"删除容器 {container_name} 失败: {e}")
    
    def _cleanup_lab_resources(self, lab_id: int):
        """清理指定 Lab 的所有资源"""
        try:
            # 停止相关容器
            containers = self.client.containers.list(all=True, filters={'label': f'lab-id={lab_id}'})
            for container in containers:
                try:
                    if container.status == 'running':
                        container.stop(timeout=10)
                    container.remove(force=True)
                    logger.info(f"清理容器 {container.name}")
                except Exception as e:
                    logger.error(f"清理容器 {container.name} 失败: {e}")
            
            # 删除网络
            self._remove_lab_network(f"lab-network-{lab_id}")
            
        except Exception as e:
            logger.error(f"清理 Lab {lab_id} 资源失败: {e}")