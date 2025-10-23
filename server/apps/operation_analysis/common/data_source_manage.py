# # -- coding: utf-8 --
# # @File: data_source_manage.py
# # @Time: 2025/8/7 10:12
# # @Author: windyzhao
# import threading
# import time
# from typing import Dict, Optional
# from datetime import datetime
#
# from nats.aio.client import Client as NatsClient
#
# from apps.operation_analysis.models import NameSpace
# from apps.core.logger import operation_analysis_logger as logger
# from nats_client.clients import get_nc_client
#
#
# class NatsPool:
#     """
#     NATS连接池
#     用于管理NATS连接，提供获取和释放连接的功能
#     采用单例模式，确保全局唯一的连接池实例
#     """
#
#     _instance = None
#     _lock = threading.Lock()
#
#     def __new__(cls):
#         """单例模式实现"""
#         if cls._instance is None:
#             with cls._lock:
#                 if cls._instance is None:
#                     cls._instance = super().__new__(cls)
#                     cls._instance._initialized = False
#         return cls._instance
#
#     def __init__(self):
#         """初始化连接池"""
#         if hasattr(self, '_initialized') and self._initialized:
#             return
#
#         self._connections: Dict[
#             int, Dict] = {}  # 存储连接信息 {namespace_id: {client: NatsClient, last_used: timestamp, healthy: bool}}
#         self._lock = threading.Lock()
#         self._max_idle_time = 300  # 最大空闲时间（秒）
#         self._health_check_interval = 60  # 健康检查间隔（秒）
#         self._initialized = True
#
#         logger.info("NATS连接池初始化完成")
#
#     async def get_connection(self, namespace_id: int) -> Optional[NatsClient]:
#         """
#         获取指定命名空间的NATS连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             NatsClient: NATS客户端连接对象，如果获取失败返回None
#         """
#         try:
#             with self._lock:
#                 # 检查是否已存在连接
#                 if namespace_id in self._connections:
#                     conn_info = self._connections[namespace_id]
#                     client = conn_info.get('client')
#
#                     # 检查连接是否健康
#                     if client and client.is_connected:
#                         conn_info['last_used'] = time.time()
#                         logger.debug(f"复用现有NATS连接: {namespace_id}")
#                         return client
#                     else:
#                         logger.warning(f"现有连接不健康，需要重新创建: {namespace_id}")
#                         self._remove_connection(namespace_id)
#
#                 # 创建新连接
#                 return await self._create_connection(namespace_id)
#
#         except Exception as e:
#             logger.error(f"获取NATS连接失败 - namespace_id: {namespace_id}, error: {e}")
#             return None
#
#     async def _create_connection(self, namespace_id: int) -> Optional[NatsClient]:
#         """
#         创建新的NATS连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             NatsClient: 新创建的NATS客户端连接
#         """
#         try:
#             # 从数据库获取命名空间配置
#             namespace = NameSpace.objects.filter(id=namespace_id, is_active=True).first()
#             if not namespace:
#                 logger.error(f"命名空间不存在或未激活: {namespace_id}")
#                 return None
#
#             logger.info(f"正在创建NATS连接 - namespace_id: {namespace_id}, name: {namespace.name}")
#
#             # 构建完整的NATS连接URL: nats://username:password@domain:port
#             # 如果domain中不包含端口，默认使用4222端口
#             if ':' not in namespace.domain:
#                 server_url = f"nats://{namespace.account}:{namespace.password}@{namespace.domain}:4222"
#             else:
#                 server_url = f"nats://{namespace.account}:{namespace.password}@{namespace.domain}"
#
#             # 使用框架的get_nc_client创建连接，传入完整的server URL
#             client = await get_nc_client(server=server_url)
#
#             # 存储连接信息
#             self._connections[namespace_id] = {
#                 'client': client,
#                 'last_used': time.time(),
#                 'created_at': datetime.now(),
#                 'healthy': True,
#                 'namespace': namespace
#             }
#
#             logger.info(f"NATS连接创建成功 - namespace_id: {namespace_id}")
#             return client
#
#         except Exception as e:
#             logger.error(f"创建NATS连接失败 - namespace_id: {namespace_id}, error: {e}")
#             return None
#
#     def release_connection(self, namespace_id: int):
#         """
#         释放指定命名空间的连接（标记为可回收，不立即关闭）
#
#         Args:
#             namespace_id: 命名空间ID
#         """
#         try:
#             with self._lock:
#                 if namespace_id in self._connections:
#                     self._connections[namespace_id]['last_used'] = time.time()
#                     logger.debug(f"标记连接为可回收: {namespace_id}")
#         except Exception as e:
#             logger.error(f"释放连接失败 - namespace_id: {namespace_id}, error: {e}")
#
#     async def close_connection(self, namespace_id: int):
#         """
#         关闭指定命名空间的连接
#
#         Args:
#             namespace_id: 命名空间ID
#         """
#         try:
#             with self._lock:
#                 if namespace_id in self._connections:
#                     conn_info = self._connections.pop(namespace_id)
#                     client = conn_info.get('client')
#
#                     if client and client.is_connected:
#                         await client.close()
#                         logger.info(f"NATS连接已关闭: {namespace_id}")
#                     else:
#                         logger.debug(f"连接已断开，无需关闭: {namespace_id}")
#
#         except Exception as e:
#             logger.error(f"关闭NATS连接失败 - namespace_id: {namespace_id}, error: {e}")
#
#     def _remove_connection(self, namespace_id: int):
#         """
#         移除连接记录（内部方法，需要在锁内调用）
#
#         Args:
#             namespace_id: 命名空间ID
#         """
#         if namespace_id in self._connections:
#             self._connections.pop(namespace_id)
#             logger.debug(f"移除连接记录: {namespace_id}")
#
#     async def cleanup_idle_connections(self):
#         """
#         清理空闲连接
#         """
#         try:
#             current_time = time.time()
#             idle_connections = []
#
#             with self._lock:
#                 for namespace_id, conn_info in list(self._connections.items()):
#                     if current_time - conn_info['last_used'] > self._max_idle_time:
#                         idle_connections.append(namespace_id)
#
#             # 关闭空闲连接
#             for namespace_id in idle_connections:
#                 logger.info(f"清理空闲连接: {namespace_id}")
#                 await self.close_connection(namespace_id)
#
#         except Exception as e:
#             logger.error(f"清理空闲连接失败: {e}")
#
#     async def health_check(self):
#         """
#         健康检查所有连接
#         """
#         try:
#             unhealthy_connections = []
#
#             with self._lock:
#                 for namespace_id, conn_info in list(self._connections.items()):
#                     client = conn_info.get('client')
#                     if not client or not client.is_connected:
#                         unhealthy_connections.append(namespace_id)
#                         conn_info['healthy'] = False
#                         logger.warning(f"检测到不健康连接: {namespace_id}")
#
#             # 移除不健康的连接
#             for namespace_id in unhealthy_connections:
#                 await self.close_connection(namespace_id)
#
#         except Exception as e:
#             logger.error(f"健康检查失败: {e}")
#
#     def get_pool_status(self) -> Dict:
#         """
#         获取连接池状态
#
#         Returns:
#             Dict: 连接池状态信息
#         """
#         try:
#             with self._lock:
#                 total_connections = len(self._connections)
#                 healthy_connections = sum(1 for conn in self._connections.values() if conn.get('healthy', False))
#
#                 status = {
#                     'total_connections': total_connections,
#                     'healthy_connections': healthy_connections,
#                     'unhealthy_connections': total_connections - healthy_connections,
#                     'connections': {}
#                 }
#
#                 for namespace_id, conn_info in self._connections.items():
#                     status['connections'][namespace_id] = {
#                         'healthy': conn_info.get('healthy', False),
#                         'last_used': conn_info.get('last_used'),
#                         'created_at': conn_info.get('created_at'),
#                         'is_connected': conn_info.get('client', {}).is_connected if conn_info.get('client') else False
#                     }
#
#                 return status
#
#         except Exception as e:
#             logger.error(f"获取连接池状态失败: {e}")
#             return {'error': str(e)}
#
#     async def close_all_connections(self):
#         """
#         关闭所有连接
#         """
#         try:
#             connection_ids = list(self._connections.keys())
#             for namespace_id in connection_ids:
#                 await self.close_connection(namespace_id)
#
#             logger.info("所有NATS连接已关闭")
#
#         except Exception as e:
#             logger.error(f"关闭所有连接失败: {e}")
#
#
# class DataSourceManges:
#     """
#     数据源管理器
#     通过数据源的ID找到对应的数据源NATS服务进行连接管理，结合NatsPool进行连接管理
#     专注于NATS连接的创建、删除和更新，不负责NameSpace模型的CRUD操作
#     """
#
#     def __init__(self):
#         """初始化数据源管理器"""
#         self.nats_pool = NatsPool()
#         logger.info("数据源管理器初始化完成")
#
#     async def create_namespace_connection(self, namespace_id: int) -> Dict:
#         """
#         为指定命名空间创建NATS连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 操作结果
#         """
#         try:
#             # 查询命名空间是否存在
#             namespace = NameSpace.objects.filter(id=namespace_id, is_active=True).first()
#             if not namespace:
#                 return {
#                     'result': False,
#                     'message': f"命名空间不存在或未激活: {namespace_id}"
#                 }
#
#             # 创建NATS连接
#             client = await self.nats_pool.get_connection(namespace_id)
#             if client:
#                 self.nats_pool.release_connection(namespace_id)
#                 logger.info(f"为命名空间创建NATS连接成功 - id: {namespace_id}, name: {namespace.name}")
#
#                 return {
#                     'result': True,
#                     'data': {
#                         'id': namespace.id,
#                         'name': namespace.name,
#                         'domain': namespace.domain,
#                         'is_active': namespace.is_active
#                     },
#                     'message': 'NATS连接创建成功'
#                 }
#             else:
#                 logger.warning(f"为命名空间创建NATS连接失败 - id: {namespace_id}, name: {namespace.name}")
#                 return {
#                     'result': False,
#                     'message': 'NATS连接创建失败'
#                 }
#
#         except Exception as e:
#             logger.error(f"创建命名空间连接失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'创建连接失败: {str(e)}'
#             }
#
#     async def update_namespace_connection(self, namespace_id: int) -> Dict:
#         """
#         更新指定命名空间的NATS连接
#         先关闭旧连接，再创建新连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 操作结果
#         """
#         try:
#             # 查询命名空间是否存在
#             namespace = NameSpace.objects.filter(id=namespace_id, is_active=True).first()
#             if not namespace:
#                 return {
#                     'result': False,
#                     'message': f"命名空间不存在或未激活: {namespace_id}"
#                 }
#
#             # 先关闭旧连接
#             await self.nats_pool.close_connection(namespace_id)
#             logger.info(f"已关闭旧NATS连接 - id: {namespace_id}")
#
#             # 创建新连接
#             client = await self.nats_pool.get_connection(namespace_id)
#             if client:
#                 self.nats_pool.release_connection(namespace_id)
#                 logger.info(f"更新命名空间NATS连接成功 - id: {namespace_id}")
#
#                 return {
#                     'result': True,
#                     'data': {
#                         'id': namespace.id,
#                         'name': namespace.name,
#                         'domain': namespace.domain,
#                         'is_active': namespace.is_active
#                     },
#                     'message': 'NATS连接更新成功'
#                 }
#             else:
#                 logger.warning(f"更新命名空间NATS连接失败 - id: {namespace_id}")
#                 return {
#                     'result': False,
#                     'message': 'NATS连接更新失败'
#                 }
#
#         except Exception as e:
#             logger.error(f"更新命名空间连接失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'更新连接失败: {str(e)}'
#             }
#
#     async def delete_namespace_connection(self, namespace_id: int) -> Dict:
#         """
#         删除指定命名空间的NATS连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 操作结果
#         """
#         try:
#             # 查询命名空间信息（用于日志记录）
#             namespace = NameSpace.objects.filter(id=namespace_id).first()
#             namespace_name = namespace.name if namespace else f"未知命名空间({namespace_id})"
#
#             # 关闭连接
#             await self.nats_pool.close_connection(namespace_id)
#             logger.info(f"删除命名空间NATS连接成功 - id: {namespace_id}, name: {namespace_name}")
#
#             return {
#                 'result': True,
#                 'message': 'NATS连接删除成功'
#             }
#
#         except Exception as e:
#             logger.error(f"删除命名空间连接失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'删除连接失败: {str(e)}'
#             }
#
#     def get_namespace_info(self, namespace_id: int) -> Dict:
#         """
#         获取单个命名空间信息
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 命名空间信息
#         """
#         try:
#             namespace = NameSpace.objects.filter(id=namespace_id).first()
#             if not namespace:
#                 return {
#                     'result': False,
#                     'message': f"命名空间不存在: {namespace_id}"
#                 }
#
#             return {
#                 'result': True,
#                 'data': {
#                     'id': namespace.id,
#                     'name': namespace.name,
#                     'account': namespace.account,
#                     'domain': namespace.domain,
#                     'desc': namespace.desc,
#                     'is_active': namespace.is_active,
#                     'created_at': namespace.created_at,
#                     'updated_at': namespace.updated_at,
#                     'created_by': namespace.created_by,
#                     'updated_by': namespace.updated_by
#                 }
#             }
#
#         except Exception as e:
#             logger.error(f"获取命名空间失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'获取失败: {str(e)}'
#             }
#
#     def list_namespaces(self, filters: Dict = None, page: int = 1, page_size: int = 20) -> Dict:
#         """
#         获取命名空间列表
#
#         Args:
#             filters: 过滤条件
#             page: 页码
#             page_size: 每页大小
#
#         Returns:
#             Dict: 命名空间列表
#         """
#         try:
#             queryset = NameSpace.objects.all()
#
#             # 应用过滤条件
#             if filters:
#                 if 'name' in filters:
#                     queryset = queryset.filter(name__icontains=filters['name'])
#                 if 'is_active' in filters:
#                     queryset = queryset.filter(is_active=filters['is_active'])
#                 if 'domain' in filters:
#                     queryset = queryset.filter(domain__icontains=filters['domain'])
#
#             # 分页
#             total_count = queryset.count()
#             start = (page - 1) * page_size
#             end = start + page_size
#             namespaces = queryset[start:end]
#
#             # 构建返回数据
#             data = []
#             for namespace in namespaces:
#                 data.append({
#                     'id': namespace.id,
#                     'name': namespace.name,
#                     'account': namespace.account,
#                     'domain': namespace.domain,
#                     'desc': namespace.desc,
#                     'is_active': namespace.is_active,
#                     'created_at': namespace.created_at,
#                     'updated_at': namespace.updated_at,
#                     'created_by': namespace.created_by,
#                     'updated_by': namespace.updated_by
#                 })
#
#             return {
#                 'result': True,
#                 'data': {
#                     'items': data,
#                     'total_count': total_count,
#                     'page': page,
#                     'page_size': page_size,
#                     'total_pages': (total_count + page_size - 1) // page_size
#                 }
#             }
#
#         except Exception as e:
#             logger.error(f"获取命名空间列表失败: {e}")
#             return {
#                 'result': False,
#                 'message': f'获取列表失败: {str(e)}'
#             }
#
#     async def test_namespace_connection(self, namespace_id: int) -> Dict:
#         """
#         测试命名空间连接
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 测试结果
#         """
#         try:
#             namespace = NameSpace.objects.filter(id=namespace_id).first()
#             if not namespace:
#                 return {
#                     'result': False,
#                     'message': f"命名空间不存在: {namespace_id}"
#                 }
#
#             # 尝试获取连接
#             client = await self.nats_pool.get_connection(namespace_id)
#
#             if client and client.is_connected:
#                 # 释放连接
#                 self.nats_pool.release_connection(namespace_id)
#
#                 logger.info(f"命名空间连接测试成功 - id: {namespace_id}")
#                 return {
#                     'result': True,
#                     'message': '连接测试成功'
#                 }
#             else:
#                 logger.warning(f"命名空间连接测试失败 - id: {namespace_id}")
#                 return {
#                     'result': False,
#                     'message': '连接测试失败'
#                 }
#
#         except Exception as e:
#             logger.error(f"测试命名空间连接失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'测试失败: {str(e)}'
#             }
#
#     def get_connection_status(self, namespace_id: int) -> Dict:
#         """
#         获取指定命名空间的连接状态
#
#         Args:
#             namespace_id: 命名空间ID
#
#         Returns:
#             Dict: 连接状态
#         """
#         try:
#             pool_status = self.nats_pool.get_pool_status()
#             connection_info = pool_status.get('connections', {}).get(namespace_id)
#
#             if connection_info:
#                 return {
#                     'result': True,
#                     'data': {
#                         'namespace_id': namespace_id,
#                         'is_connected': connection_info.get('is_connected', False),
#                         'healthy': connection_info.get('healthy', False),
#                         'last_used': connection_info.get('last_used'),
#                         'created_at': connection_info.get('created_at')
#                     }
#                 }
#             else:
#                 return {
#                     'result': True,
#                     'data': {
#                         'namespace_id': namespace_id,
#                         'is_connected': False,
#                         'healthy': False,
#                         'message': '无活动连接'
#                     }
#                 }
#         except Exception as e:
#             logger.error(f"获取连接状态失败 - id: {namespace_id}, error: {e}")
#             return {
#                 'result': False,
#                 'message': f'获取状态失败: {str(e)}'
#             }
#
#     def get_pool_status(self) -> Dict:
#         """
#         获取连接池状态
#
#         Returns:
#             Dict: 连接池状态
#         """
#         return self.nats_pool.get_pool_status()
#
#     async def cleanup_connections(self):
#         """
#         清理连接（清理空闲连接和执行健康检查）
#         """
#         try:
#             await self.nats_pool.cleanup_idle_connections()
#             await self.nats_pool.health_check()
#             logger.info("连接清理完成")
#         except Exception as e:
#             logger.error(f"清理连接失败: {e}")
