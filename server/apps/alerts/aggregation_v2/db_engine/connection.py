# -- coding: utf-8 --
"""
DuckDB 连接池

管理 DuckDB 连接，支持连接复用和并发控制
"""
import duckdb
import threading
from contextlib import contextmanager

from apps.core.logger import alert_logger as logger
from apps.alerts.aggregation_v2.config import AggregationV2Config


class DuckDBConnectionPool:
    """
    DuckDB 连接池
    
    特性：
    1. 线程本地连接（DuckDB 连接不支持跨线程）
    2. 自动初始化配置
    3. 连接复用
    """

    _local = threading.local()
    _lock = threading.Lock()

    @classmethod
    def get_connection(cls) -> duckdb.DuckDBPyConnection:
        """
        获取当前线程的 DuckDB 连接
        
        Returns:
            DuckDB 连接对象
        """
        if not hasattr(cls._local, 'connection') or cls._local.connection is None:
            with cls._lock:
                # 双重检查锁定
                if not hasattr(cls._local, 'connection') or cls._local.connection is None:
                    cls._local.connection = cls._create_connection()
                    logger.info(f"创建新的 DuckDB 连接: 线程={threading.current_thread().name}")

        return cls._local.connection

    @classmethod
    def _create_connection(cls) -> duckdb.DuckDBPyConnection:
        """
        创建并配置新的 DuckDB 连接
        
        Returns:
            配置好的 DuckDB 连接
        """
        # 创建内存数据库连接
        conn = duckdb.connect(database=':memory:')

        # 应用配置
        cls._apply_config(conn)

        return conn

    @classmethod
    def _apply_config(cls, conn: duckdb.DuckDBPyConnection) -> None:
        """
        应用 DuckDB 配置
        
        Args:
            conn: DuckDB 连接对象
        """
        # 设置线程数
        conn.execute(f"SET threads TO {AggregationV2Config.DUCKDB_THREADS}")

        # 设置内存限制
        conn.execute(f"SET memory_limit = '{AggregationV2Config.DUCKDB_MEMORY_LIMIT}'")

        logger.debug(
            f"DuckDB 配置: threads={AggregationV2Config.DUCKDB_THREADS}, "
            f"memory={AggregationV2Config.DUCKDB_MEMORY_LIMIT}"
        )

    @classmethod
    @contextmanager
    def connection_context(cls):
        """
        连接上下文管理器（确保异常时连接不被破坏）
        
        Yields:
            DuckDB 连接对象
            
        Examples:
            >>> with DuckDBConnectionPool.connection_context() as conn:
            ...     result = conn.execute("SELECT 1").fetchall()
        """
        conn = cls.get_connection()
        try:
            yield conn
        except Exception as e:
            logger.error(f"DuckDB 连接异常: {e}")
            # 重置连接
            cls._local.connection = None
            raise

    @classmethod
    def close_connection(cls) -> None:
        """
        关闭当前线程的连接
        """
        if hasattr(cls._local, 'connection') and cls._local.connection is not None:
            try:
                cls._local.connection.close()
                logger.info(f"关闭 DuckDB 连接: 线程={threading.current_thread().name}")
            except Exception as e:
                logger.warning(f"关闭 DuckDB 连接失败: {e}")
            finally:
                cls._local.connection = None

    @classmethod
    def close_all_connections(cls) -> None:
        """
        关闭所有连接（通常在应用关闭时调用）
        """
        # 注意：这只能关闭当前线程的连接
        # 其他线程的连接需要在各自线程中关闭
        cls.close_connection()
