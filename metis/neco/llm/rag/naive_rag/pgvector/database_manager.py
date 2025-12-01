from typing import List, Dict, Any, Optional
import psycopg
from loguru import logger

from neco.llm.rag.naive_rag.pgvector.database_connection_pool import DatabaseConnectionPool
from neco.core.utils.timing_decorator import timeit


class DatabaseManager:
    """数据库操作管理器 - 职责分离"""

    def __init__(self, db_uri: str):
        self.db_uri = self._convert_uri(db_uri)
        self._pool = DatabaseConnectionPool(self.db_uri)

    def _convert_uri(self, uri: str) -> str:
        """将SQLAlchemy格式的URI转换为psycopg支持的格式"""
        if uri.startswith('postgresql+psycopg://'):
            uri = uri.replace('postgresql+psycopg://', 'postgresql://')
        elif uri.startswith('postgres+psycopg://'):
            uri = uri.replace('postgres+psycopg://', 'postgresql://')
        return uri

    @timeit("SQL查询执行")
    def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """执行SQL查询"""
        try:
            with self._pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or {})
                    conn.commit()

                    result_count = 0
                    if cur.description:
                        columns = [desc[0] for desc in cur.description]
                        results = [dict(zip(columns, row))
                                   for row in cur.fetchall()]
                        result_count = len(results)
                    else:
                        results = []

                    logger.info(f"SQL查询完成 - 结果数: {result_count}")
                    return results
        except psycopg.OperationalError as e:
            logger.error(f"数据库连接失败 - 错误: {str(e)}")
            raise RuntimeError(f"数据库连接失败: {str(e)}") from e
        except psycopg.Error as e:
            logger.error(f"SQL查询失败 - 错误: {str(e)}")
            raise RuntimeError(f"数据库查询操作失败: {str(e)}") from e
        except Exception as e:
            logger.error(f"SQL查询异常 - 错误: {str(e)}")
            raise RuntimeError(f"数据库查询操作失败: {str(e)}") from e

    @timeit("SQL更新执行")
    def execute_update(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """执行UPDATE/DELETE等非查询SQL，返回影响的行数"""
        try:
            with self._pool.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params or {})
                    affected_rows = cur.rowcount
                    conn.commit()

                    logger.info(f"SQL更新完成 - 影响行数: {affected_rows}")
                    return affected_rows
        except psycopg.OperationalError as e:
            logger.error(f"数据库连接失败 - 错误: {str(e)}")
            raise RuntimeError(f"数据库连接失败: {str(e)}") from e
        except psycopg.Error as e:
            logger.error(f"SQL更新失败 - 错误: {str(e)}")
            raise RuntimeError(f"数据库更新操作失败: {str(e)}") from e
        except Exception as e:
            logger.error(f"SQL更新异常 - 错误: {str(e)}")
            raise RuntimeError(f"数据库更新操作失败: {str(e)}") from e
