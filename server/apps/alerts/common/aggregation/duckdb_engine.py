# -- coding: utf-8 --
# @File: duckdb_engine.py
# @Time: 2025/9/15 15:06
# @Author: windyzhao
from typing import Any, Dict, List, Tuple
import duckdb
import pandas as pd
from contextlib import contextmanager
from apps.core.logger import alert_logger as logger

"""
使用DuckDB进行事件聚合处理的引擎模块

DuckDB特点：
- 内存分析数据库，擅长OLAP查询
- 支持复杂的SQL分析函数
- 与Pandas无缝集成
- 支持JSON数据处理
- 高性能的窗口函数和聚合操作
"""

# 模块级别的默认配置
# DuckDB 默认配置
DEFAULT_DUCKDB_CONFIG = {
    'memory_limit': '512MB',  # 使用具体的内存单位而不是百分比
    'threads': 2,
    'max_memory': '1GB'
}


class DuckDBEngine:
    """
    DuckDB引擎，用于高效处理大规模事件数据的聚合
    
    功能特性：
    - 支持内存和持久化连接
    - 提供事务管理
    - 支持Pandas DataFrame互操作
    - 内置查询性能监控
    - 支持连接池管理
    """

    def __init__(self, connection_params: dict = None):
        """
        初始化DuckDB连接
        
        Args:
            connection_params: 连接参数字典
                - database: 数据库文件路径，默认':memory:'为内存数据库
                - read_only: 是否只读模式，默认False
                - config: DuckDB配置参数字典
        """
        if connection_params is None:
            connection_params = DEFAULT_DUCKDB_CONFIG

        self.database = connection_params.get('database', ':memory:')
        self.config = connection_params.get('config', {})

        self.connection = None
        self._connect()

    def _connect(self):
        """建立DuckDB连接"""
        try:
            self.connection = duckdb.connect(
                database=self.database,
                config=self.config
            )

            # 启用相关扩展
            # self._enable_extensions()

            logger.info(f"DuckDB connection established: {self.database}")
        except Exception as e:
            logger.error(f"Failed to connect to DuckDB: {e}")
            raise

    def _enable_extensions(self):
        """启用DuckDB扩展"""
        try:
            # 启用JSON扩展
            self.connection.execute("INSTALL json; LOAD json;")
            # 启用HTTP扩展（用于远程数据访问）
            self.connection.execute("INSTALL httpfs; LOAD httpfs;")
            logger.debug("DuckDB extensions enabled successfully")
        except Exception as e:
            logger.warning(f"Some DuckDB extensions failed to load: {e}")

    def execute_query(self, query: str, params: dict = None) -> List[Tuple]:
        """
        执行DuckDB查询并返回结果
        
        Args:
            query: SQL查询字符串
            params: 可选的查询参数字典
        Returns:
            查询结果列表
        """
        if params is None:
            params = {}
        try:
            logger.debug(f"Executing query: {query[:100]}...")
            result = self.connection.execute(query, params).fetchall()
            logger.debug(f"Query executed successfully, returned {len(result)} rows")
            return result
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query}")
            raise

    def execute_query_to_df(self, query: str, params: dict = None) -> pd.DataFrame:
        """
        执行查询并返回Pandas DataFrame
        
        Args:
            query: SQL查询字符串  
            params: 可选的查询参数字典
        Returns:
            Pandas DataFrame
        """
        if params is None:
            params = {}

        try:
            logger.debug(f"Executing query to DataFrame: {query[:100]}...")
            result = self.connection.execute(query, params).df()
            logger.debug(f"Query executed successfully, returned DataFrame with shape {result.shape}")
            return result
        except Exception as e:
            logger.error(f"Query to DataFrame failed: {e}")
            logger.error(f"Query: {query}")
            raise

    def load_dataframe(self, df: pd.DataFrame, table_name: str, if_exists: str = 'replace') -> bool:
        """
        将Pandas DataFrame加载到DuckDB表中
        
        Args:
            df: Pandas DataFrame
            table_name: 目标表名
            if_exists: 如果表存在的处理方式 ('replace', 'append', 'fail')
        Returns:
            是否成功
        """
        try:
            if if_exists == 'replace':
                self.connection.execute(f"DROP TABLE IF EXISTS {table_name}")
            elif if_exists == 'fail':
                # 检查表是否存在
                exists_query = f"""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_name = '{table_name}'
                """
                if self.connection.execute(exists_query).fetchone()[0] > 0:
                    raise ValueError(f"Table {table_name} already exists")

            # 创建表并插入数据
            self.connection.register(table_name, df)

            logger.info(f"DataFrame loaded to table '{table_name}' with {len(df)} rows")
            return True
        except Exception as e:
            logger.error(f"Failed to load DataFrame to table '{table_name}': {e}")
            return False

    def create_table_from_events(self, events_data: List[dict], table_name: str = 'events') -> bool:
        """
        从事件数据创建DuckDB表
        
        Args:
            events_data: 事件数据列表
            table_name: 表名
        Returns:
            是否成功
        """
        try:
            df = pd.DataFrame(events_data)
            return self.load_dataframe(df, table_name)
        except Exception as e:
            logger.error(f"Failed to create table from events: {e}")
            return False

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        获取表信息
        
        Args:
            table_name: 表名
        Returns:
            表信息字典
        """
        try:
            # 获取表结构
            schema_query = f"DESCRIBE {table_name}"
            schema_result = self.execute_query(schema_query)

            # 获取行数
            count_query = f"SELECT COUNT(*) FROM {table_name}"
            row_count = self.execute_query(count_query)[0][0]

            return {
                'table_name': table_name,
                'row_count': row_count,
                'schema': schema_result,
                'columns': [row[0] for row in schema_result]
            }
        except Exception as e:
            logger.error(f"Failed to get table info for '{table_name}': {e}")
            return {}

    @contextmanager
    def transaction(self):
        """
        事务上下文管理器
        
        Usage:
            with engine.transaction():
                engine.execute_query("INSERT ...")
                engine.execute_query("UPDATE ...")
        """
        try:
            self.connection.execute("BEGIN TRANSACTION")
            yield self.connection
            self.connection.execute("COMMIT")
        except Exception as e:
            self.connection.execute("ROLLBACK")
            logger.error(f"Transaction rolled back due to error: {e}")
            raise

    def analyze_query_performance(self, query: str) -> Dict[str, Any]:
        """
        分析查询性能
        
        Args:
            query: SQL查询
        Returns:
            性能分析结果
        """
        try:
            # 启用性能分析
            self.connection.execute("PRAGMA enable_profiling")

            # 执行查询
            import time
            start_time = time.time()
            result = self.execute_query(query)
            execution_time = time.time() - start_time

            # 获取查询计划
            explain_query = f"EXPLAIN {query}"
            query_plan = self.execute_query(explain_query)

            return {
                'execution_time_seconds': execution_time,
                'row_count': len(result),
                'query_plan': query_plan
            }
        except Exception as e:
            logger.error(f"Failed to analyze query performance: {e}")
            return {}

    def optimize_for_aggregation(self):
        """
        为聚合查询优化DuckDB设置
        """
        optimization_settings = [
            "SET enable_optimizer=true",
            "SET enable_profiling='query_tree_optimizer'",
            "SET preserve_insertion_order=false",
            "SET enable_progress_bar=true",
        ]

        for setting in optimization_settings:
            try:
                self.connection.execute(setting)
                logger.debug(f"Applied optimization: {setting}")
            except Exception as e:
                logger.warning(f"Failed to apply optimization '{setting}': {e}")

    def close(self):
        """关闭DuckDB连接"""
        if self.connection:
            try:
                self.connection.close()
                logger.info("DuckDB connection closed")
            except Exception as e:
                logger.error(f"Error closing DuckDB connection: {e}")
            finally:
                self.connection = None

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close()

    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            连接是否正常
        """
        try:
            self.connection.execute("SELECT 1").fetchone()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_memory_usage(self) -> Dict[str, Any]:
        """
        获取内存使用情况
        
        Returns:
            内存使用信息
        """
        try:
            memory_query = "PRAGMA database_size"
            size_result = self.execute_query(memory_query)

            return {
                'database_size_bytes': size_result[0][0] if size_result else 0,
                'connection_type': 'memory' if self.database == ':memory:' else 'file'
            }
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return {}
