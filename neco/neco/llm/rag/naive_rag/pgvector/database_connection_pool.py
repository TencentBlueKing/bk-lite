from contextlib import contextmanager
from threading import Lock
import psycopg
from loguru import logger


class DatabaseConnectionPool:
    """简单的数据库连接池实现"""

    def __init__(self, uri: str, max_connections: int = 10):
        self.uri = uri
        self.max_connections = max_connections
        self._connections = []
        self._lock = Lock()
        self._created_count = 0

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = self._acquire_connection()
            yield conn
        finally:
            if conn:
                self._release_connection(conn)

    def _acquire_connection(self):
        """获取连接"""
        with self._lock:
            # 尝试从池中获取可用连接
            while self._connections:
                conn = self._connections.pop()
                try:
                    # 检查连接是否仍然有效
                    conn.execute("SELECT 1")
                    return conn
                except (psycopg.Error, psycopg.OperationalError):
                    # 连接已失效，关闭并继续寻找
                    try:
                        conn.close()
                    except:
                        pass
                    self._created_count -= 1

            # 池中无可用连接，创建新连接
            if self._created_count < self.max_connections:
                try:
                    conn = psycopg.connect(self.uri, connect_timeout=30)
                    self._created_count += 1
                    return conn
                except Exception as e:
                    logger.error(f"创建数据库连接失败: {e}")
                    raise
            else:
                raise RuntimeError("连接池已满，无法创建新连接")

    def _release_connection(self, conn):
        """释放连接回池中"""
        if not conn.closed:
            with self._lock:
                if len(self._connections) < self.max_connections:
                    self._connections.append(conn)
                    return

        # 池已满或连接已关闭，直接关闭连接
        try:
            conn.close()
        except:
            pass
        with self._lock:
            self._created_count -= 1
