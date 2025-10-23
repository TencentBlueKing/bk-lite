# -*- coding: utf-8 -*-
"""
Kubernetes Lab 客户端
基于 Kubernetes 运行时管理 Lab 环境
"""

import yaml
from typing import Dict, Any, List, Optional
from django.conf import settings
from kubernetes import client, config

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.config import KUBE_NAMESPACE


class KubernetesLabClient:
    """Kubernetes Lab 环境管理客户端"""
    
    def __init__(self):
        """初始化 Kubernetes 客户端"""
        try:
            if getattr(settings, 'KUBE_CONFIG_FILE', '') == "":
                config.load_incluster_config()
            else:
                config.load_kube_config(config_file=settings.KUBE_CONFIG_FILE)
            
            self.core_api = client.CoreV1Api()
            self.apps_api = client.AppsV1Api()
            self.networking_api = client.NetworkingV1Api()
            self.custom_objects_api = client.CustomObjectsApi()
            
            self.namespace = KUBE_NAMESPACE
            self.traefik_group = "traefik.io"
            self.traefik_version = "v1alpha1"
            
            logger.info("Kubernetes Lab 客户端初始化成功")
            
        except Exception as e:
            logger.error(f"Kubernetes Lab 客户端初始化失败: {e}")
            raise Exception("无法连接到 Kubernetes 服务，请检查配置和权限")
    
    def start_lab_env(self, lab_env) -> Dict[str, Any]:
        """
        启动 Lab 环境
        
        在 Kubernetes 中，我们使用 StatefulSet 来部署多容器的 Lab 环境
        """
        try:
            lab_id = lab_env.id
            
            # 1. 创建 StatefulSet（包含 IDE 和基础设施容器）
            statefulset_result = self._create_lab_statefulset(lab_env)
            if not statefulset_result.get('success'):
                return statefulset_result
            
            # 2. 创建 Service
            service_result = self._create_lab_service(lab_env)
            if not service_result.get('success'):
                self._cleanup_lab_resources(lab_id)
                return service_result
            
            # 3. 创建 Ingress（如果需要外部访问）
            ingress_result = self._create_lab_ingress(lab_env)
            
            endpoint = self._get_lab_endpoint(lab_env)
            
            return {
                'success': True,
                'endpoint': endpoint,
                'message': f'Lab 环境 {lab_id} 启动成功'
            }
            
        except Exception as e:
            logger.exception(f"启动 Lab 环境 {lab_env.id} 异常: {e}")
            self._cleanup_lab_resources(lab_env.id)
            return {'success': False, 'message': f'启动异常: {str(e)}'}
    
    def stop_lab_env(self, lab_env) -> Dict[str, Any]:
        """停止 Lab 环境"""
        try:
            lab_id = lab_env.id
            
            # 删除 Ingress
            self._delete_lab_ingress(lab_id)
            
            # 删除 Service
            self._delete_lab_service(lab_id)
            
            # 删除 StatefulSet
            self._delete_lab_statefulset(lab_id)
            
            return {'success': True, 'message': f'Lab 环境 {lab_id} 停止成功'}
            
        except Exception as e:
            logger.exception(f"停止 Lab 环境 {lab_env.id} 异常: {e}")
            return {'success': False, 'message': f'停止异常: {str(e)}'}
    
    def get_lab_env_status(self, lab_env) -> Dict[str, Any]:
        """获取 Lab 环境运行时状态"""
        try:
            lab_id = lab_env.id
            statefulset_name = f"lab-env-{lab_id}"
            
            # 获取 StatefulSet 状态
            try:
                statefulset = self.apps_api.read_namespaced_stateful_set(
                    name=statefulset_name,
                    namespace=self.namespace
                )
                statefulset_status = {
                    'ready_replicas': statefulset.status.ready_replicas or 0,
                    'replicas': statefulset.status.replicas or 0,
                    'current_replicas': statefulset.status.current_replicas or 0
                }
            except client.exceptions.ApiException as e:
                if e.status == 404:
                    statefulset_status = {'status': 'not_found'}
                else:
                    statefulset_status = {'status': 'error', 'message': str(e)}
            
            # 获取 Pod 状态
            pod_statuses = []
            try:
                pods = self.core_api.list_namespaced_pod(
                    namespace=self.namespace,
                    label_selector=f"app=lab-env,lab-id={lab_id}"
                )
                for pod in pods.items:
                    pod_statuses.append({
                        'name': pod.metadata.name,
                        'phase': pod.status.phase,
                        'ready': all(cs.ready for cs in pod.status.container_statuses or []),
                        'container_count': len(pod.spec.containers)
                    })
            except Exception as e:
                logger.error(f"获取 Pod 状态失败: {e}")
            
            return {
                'runtime': 'kubernetes',
                'namespace': self.namespace,
                'statefulset': statefulset_status,
                'pods': pod_statuses,
                'service': f"lab-env-{lab_id}-service"
            }
            
        except Exception as e:
            logger.exception(f"获取 Lab 环境 {lab_env.id} 运行时状态异常: {e}")
            return {'error': str(e)}
    
    def get_infra_instance_status(self, instance) -> Dict[str, Any]:
        """获取基础设施实例运行时状态"""
        # 在 Kubernetes 实现中，基础设施实例作为 Pod 中的 sidecar 容器运行
        # 状态信息包含在整个 Lab 环境的状态中
        return {'status': 'part_of_lab_env', 'instance_id': instance.id}
    
    def list_running_lab_envs(self) -> List[Dict[str, Any]]:
        """列出所有运行中的 Lab 环境"""
        try:
            statefulsets = self.apps_api.list_namespaced_stateful_set(
                namespace=self.namespace,
                label_selector="app=lab-env"
            )
            
            lab_envs = []
            for sts in statefulsets.items:
                labels = sts.metadata.labels or {}
                lab_id = labels.get('lab-id')
                if lab_id:
                    lab_envs.append({
                        'lab_id': lab_id,
                        'statefulset_name': sts.metadata.name,
                        'ready_replicas': sts.status.ready_replicas or 0,
                        'replicas': sts.status.replicas or 0
                    })
            
            return lab_envs
            
        except Exception as e:
            logger.exception(f"列出运行中的 Lab 环境异常: {e}")
            return []
    
    def cleanup_orphaned_resources(self) -> Dict[str, Any]:
        """清理孤儿资源"""
        try:
            # 获取数据库中的有效 lab_id
            from apps.lab.models import LabEnv
            valid_lab_ids = set(str(lab.id) for lab in LabEnv.objects.all())
            
            cleaned_resources = {
                'statefulsets': [],
                'services': [],
                'ingresses': []
            }
            
            # 清理 StatefulSets
            statefulsets = self.apps_api.list_namespaced_stateful_set(
                namespace=self.namespace,
                label_selector="app=lab-env"
            )
            for sts in statefulsets.items:
                lab_id = sts.metadata.labels.get('lab-id')
                if lab_id and lab_id not in valid_lab_ids:
                    self.apps_api.delete_namespaced_stateful_set(
                        name=sts.metadata.name,
                        namespace=self.namespace
                    )
                    cleaned_resources['statefulsets'].append(sts.metadata.name)
                    logger.info(f"清理孤儿 StatefulSet: {sts.metadata.name}")
            
            # 清理 Services
            services = self.core_api.list_namespaced_service(
                namespace=self.namespace,
                label_selector="app=lab-env"
            )
            for svc in services.items:
                lab_id = svc.metadata.labels.get('lab-id')
                if lab_id and lab_id not in valid_lab_ids:
                    self.core_api.delete_namespaced_service(
                        name=svc.metadata.name,
                        namespace=self.namespace
                    )
                    cleaned_resources['services'].append(svc.metadata.name)
                    logger.info(f"清理孤儿 Service: {svc.metadata.name}")
            
            return {
                'success': True,
                **cleaned_resources
            }
            
        except Exception as e:
            logger.exception(f"清理孤儿资源异常: {e}")
            return {'success': False, 'message': str(e)}
    
    def _create_lab_statefulset(self, lab_env) -> Dict[str, Any]:
        """创建 Lab StatefulSet"""
        try:
            lab_id = lab_env.id
            statefulset_name = f"lab-env-{lab_id}"
            
            # 构建容器列表：IDE 容器 + 基础设施容器
            containers = []
            
            # 1. IDE 容器（主容器）
            ide_container = self._build_ide_container(lab_env)
            containers.append(ide_container)
            
            # 2. 基础设施容器（sidecar 容器）
            for instance in lab_env.infra_instances.all():
                infra_container = self._build_infra_container(instance)
                containers.append(infra_container)
            
            # 构建 StatefulSet 规格
            statefulset_spec = {
                'apiVersion': 'apps/v1',
                'kind': 'StatefulSet',
                'metadata': {
                    'name': statefulset_name,
                    'namespace': self.namespace,
                    'labels': {
                        'app': 'lab-env',
                        'lab-id': str(lab_id)
                    }
                },
                'spec': {
                    'serviceName': f"lab-env-{lab_id}-service",
                    'replicas': 1,
                    'selector': {
                        'matchLabels': {
                            'app': 'lab-env',
                            'lab-id': str(lab_id)
                        }
                    },
                    'template': {
                        'metadata': {
                            'labels': {
                                'app': 'lab-env',
                                'lab-id': str(lab_id)
                            }
                        },
                        'spec': {
                            'containers': containers,
                            'volumes': self._build_volumes(lab_env)
                        }
                    },
                    'volumeClaimTemplates': self._build_volume_claim_templates(lab_env)
                }
            }
            
            # 创建 StatefulSet
            self.apps_api.create_namespaced_stateful_set(
                namespace=self.namespace,
                body=statefulset_spec
            )
            
            logger.info(f"创建 StatefulSet {statefulset_name} 成功")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"创建 StatefulSet 失败: {e}")
            return {'success': False, 'message': str(e)}
    
    def _build_ide_container(self, lab_env) -> Dict[str, Any]:
        """构建 IDE 容器规格"""
        return {
            'name': 'ide',
            'image': f"{lab_env.ide_image.name}:{lab_env.ide_image.version}",
            'ports': [
                {'containerPort': 8888, 'name': 'http', 'protocol': 'TCP'}
            ],
            'env': [
                {'name': 'LAB_ENV_ID', 'value': str(lab_env.id)},
                {'name': 'LAB_ENV_NAME', 'value': lab_env.name},
                {'name': 'TZ', 'value': 'Asia/Shanghai'}
            ],
            'volumeMounts': [
                {
                    'name': 'workspace',
                    'mountPath': '/workspace'
                }
            ],
            'resources': {
                'requests': {
                    'cpu': f"{lab_env.cpu}",
                    'memory': lab_env.memory
                },
                'limits': {
                    'cpu': f"{lab_env.cpu}",
                    'memory': lab_env.memory
                }
            }
        }
    
    def _build_infra_container(self, instance) -> Dict[str, Any]:
        """构建基础设施容器规格"""
        container = {
            'name': f"infra-{instance.id}",
            'image': f"{instance.image.name}:{instance.image.version}",
            'env': [
                {'name': 'TZ', 'value': 'Asia/Shanghai'}
            ]
        }
        
        # 添加自定义环境变量
        for key, value in instance.env_vars.items():
            container['env'].append({'name': key, 'value': str(value)})
        
        # 添加端口
        if instance.port_mappings:
            ports = []
            for container_port in instance.port_mappings.keys():
                ports.append({
                    'containerPort': int(container_port),
                    'protocol': 'TCP'
                })
            container['ports'] = ports
        
        # 添加命令和参数
        if instance.command:
            container['command'] = instance.command
        if instance.args:
            container['args'] = instance.args
        
        # 添加资源限制
        if instance.cpu_limit or instance.memory_limit:
            resources = {'limits': {}, 'requests': {}}
            if instance.cpu_limit:
                resources['limits']['cpu'] = instance.cpu_limit
                resources['requests']['cpu'] = instance.cpu_limit
            if instance.memory_limit:
                resources['limits']['memory'] = instance.memory_limit
                resources['requests']['memory'] = instance.memory_limit
            container['resources'] = resources
        
        return container
    
    def _build_volumes(self, lab_env) -> List[Dict[str, Any]]:
        """构建 Volume 配置"""
        # 这里可以添加 ConfigMap、Secret 等配置
        return []
    
    def _build_volume_claim_templates(self, lab_env) -> List[Dict[str, Any]]:
        """构建 PVC 模板"""
        return [
            {
                'metadata': {
                    'name': 'workspace'
                },
                'spec': {
                    'accessModes': ['ReadWriteOnce'],
                    'resources': {
                        'requests': {
                            'storage': lab_env.volume_size
                        }
                    }
                }
            }
        ]
    
    def _create_lab_service(self, lab_env) -> Dict[str, Any]:
        """创建 Lab Service"""
        try:
            lab_id = lab_env.id
            service_name = f"lab-env-{lab_id}-service"
            
            # 构建端口列表
            ports = [
                {
                    'name': 'http',
                    'port': 8888,
                    'targetPort': 8888,
                    'protocol': 'TCP'
                }
            ]
            
            # 添加基础设施实例的端口
            for instance in lab_env.infra_instances.all():
                for container_port, _ in instance.port_mappings.items():
                    ports.append({
                        'name': f"infra-{instance.id}-{container_port}",
                        'port': int(container_port),
                        'targetPort': int(container_port),
                        'protocol': 'TCP'
                    })
            
            service_spec = {
                'apiVersion': 'v1',
                'kind': 'Service',
                'metadata': {
                    'name': service_name,
                    'namespace': self.namespace,
                    'labels': {
                        'app': 'lab-env',
                        'lab-id': str(lab_id)
                    }
                },
                'spec': {
                    'type': 'ClusterIP',
                    'selector': {
                        'app': 'lab-env',
                        'lab-id': str(lab_id)
                    },
                    'ports': ports
                }
            }
            
            self.core_api.create_namespaced_service(
                namespace=self.namespace,
                body=service_spec
            )
            
            logger.info(f"创建 Service {service_name} 成功")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"创建 Service 失败: {e}")
            return {'success': False, 'message': str(e)}
    
    def _create_lab_ingress(self, lab_env) -> Dict[str, Any]:
        """创建 Lab Ingress（使用 Traefik IngressRoute）"""
        try:
            lab_id = lab_env.id
            ingress_name = f"lab-env-{lab_id}"
            
            # 如果没有配置域名，则不创建 Ingress
            if not hasattr(lab_env, 'domain') or not lab_env.domain:
                logger.info(f"Lab 环境 {lab_id} 未配置域名，跳过创建 Ingress")
                return {'success': True, 'message': 'No domain configured'}
            
            ingress_route = {
                'apiVersion': f"{self.traefik_group}/{self.traefik_version}",
                'kind': 'IngressRoute',
                'metadata': {
                    'name': ingress_name,
                    'namespace': self.namespace,
                    'labels': {
                        'app': 'lab-env',
                        'lab-id': str(lab_id)
                    }
                },
                'spec': {
                    'entryPoints': ['https'],
                    'routes': [
                        {
                            'match': f"Host(`{lab_env.domain}`)",
                            'kind': 'Rule',
                            'services': [
                                {
                                    'name': f"lab-env-{lab_id}-service",
                                    'port': 8888
                                }
                            ]
                        }
                    ],
                    'tls': {}
                }
            }
            
            self.custom_objects_api.create_namespaced_custom_object(
                group=self.traefik_group,
                version=self.traefik_version,
                namespace=self.namespace,
                plural='ingressroutes',
                body=ingress_route
            )
            
            logger.info(f"创建 IngressRoute {ingress_name} 成功")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"创建 IngressRoute 失败: {e}")
            return {'success': False, 'message': str(e)}
    
    def _get_lab_endpoint(self, lab_env) -> str:
        """获取 Lab 环境访问端点"""
        lab_id = lab_env.id
        
        # 如果配置了域名，返回 HTTPS 地址
        if hasattr(lab_env, 'domain') and lab_env.domain:
            return f"https://{lab_env.domain}"
        
        # 否则返回集群内部地址
        return f"http://lab-env-{lab_id}-service.{self.namespace}.svc.cluster.local:8888"
    
    def _delete_lab_statefulset(self, lab_id: int):
        """删除 Lab StatefulSet"""
        try:
            statefulset_name = f"lab-env-{lab_id}"
            self.apps_api.delete_namespaced_stateful_set(
                name=statefulset_name,
                namespace=self.namespace
            )
            logger.info(f"删除 StatefulSet {statefulset_name} 成功")
        except client.exceptions.ApiException as e:
            if e.status != 404:  # 忽略资源不存在的错误
                logger.error(f"删除 StatefulSet 失败: {e}")
        except Exception as e:
            logger.error(f"删除 StatefulSet 失败: {e}")
    
    def _delete_lab_service(self, lab_id: int):
        """删除 Lab Service"""
        try:
            service_name = f"lab-env-{lab_id}-service"
            self.core_api.delete_namespaced_service(
                name=service_name,
                namespace=self.namespace
            )
            logger.info(f"删除 Service {service_name} 成功")
        except client.exceptions.ApiException as e:
            if e.status != 404:
                logger.error(f"删除 Service 失败: {e}")
        except Exception as e:
            logger.error(f"删除 Service 失败: {e}")
    
    def _delete_lab_ingress(self, lab_id: int):
        """删除 Lab Ingress"""
        try:
            ingress_name = f"lab-env-{lab_id}"
            self.custom_objects_api.delete_namespaced_custom_object(
                group=self.traefik_group,
                version=self.traefik_version,
                namespace=self.namespace,
                plural='ingressroutes',
                name=ingress_name
            )
            logger.info(f"删除 IngressRoute {ingress_name} 成功")
        except client.exceptions.ApiException as e:
            if e.status != 404:
                logger.error(f"删除 IngressRoute 失败: {e}")
        except Exception as e:
            logger.error(f"删除 IngressRoute 失败: {e}")
    
    def _cleanup_lab_resources(self, lab_id: int):
        """清理指定 Lab 的所有资源"""
        try:
            self._delete_lab_ingress(lab_id)
            self._delete_lab_service(lab_id)
            self._delete_lab_statefulset(lab_id)
            logger.info(f"清理 Lab {lab_id} 所有资源完成")
        except Exception as e:
            logger.error(f"清理 Lab {lab_id} 资源失败: {e}")