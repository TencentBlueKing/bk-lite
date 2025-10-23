# -- coding: utf-8 --
# @File: graph_client.py
# @Time: 2025/9/2 15:46
# @Author: windyzhao

import os
from apps.core.logger import cmdb_logger as logger


class GraphClient:
    """
    图数据库客户端统一接口
    根据环境变量动态选择底层驱动（FalkorDB 或 Neo4j）
    支持标准的实例化和上下文管理器使用
    """

    # 支持的驱动类型
    DRIVER_FALKORDB = 'falkordb'
    DRIVER_NEO4J = 'neo4j'

    def __init__(self, **kwargs):
        """
        初始化图数据库客户端

        Args:
            **kwargs: 传递给底层客户端的参数
        """
        self._client = None
        self._kwargs = kwargs
        self._init_client()

    def _init_client(self):
        """初始化图数据库客户端"""
        driver_type = self._get_driver_type()
        logger.info(f"Initializing graph client with driver: {driver_type}")

        if driver_type == self.DRIVER_FALKORDB:
            from apps.cmdb.graph.falkordb import FalkorDBClient
            self._client = FalkorDBClient()
        elif driver_type == self.DRIVER_NEO4J:
            from apps.cmdb.graph.neo4j import Neo4jClient
            self._client = Neo4jClient()
        else:
            raise ValueError(f"Unsupported graph driver type: {driver_type}")

    def _get_driver_type(self) -> str:
        """从环境变量获取驱动类型"""
        falkordb_host = os.getenv('FALKORDB_HOST', "")
        if falkordb_host:
            return self.DRIVER_FALKORDB
        else:
            return self.DRIVER_NEO4J

    def __getattr__(self, name):
        """
        代理所有底层客户端的方法和属性

        Args:
            name: 方法或属性名

        Returns:
            底层客户端的方法或属性
        """
        if self._client is None:
            raise RuntimeError("Graph client not initialized")
        return getattr(self._client, name)

    def close(self):
        """关闭客户端连接"""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.error(f"Failed to close graph client: {str(e)}")

    def __enter__(self):
        """上下文管理器入口"""
        if hasattr(self._client, '__enter__'):
            self._client.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        if hasattr(self._client, '__exit__'):
            return self._client.__exit__(exc_type, exc_val, exc_tb)
        else:
            self.close()
