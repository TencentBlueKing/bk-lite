# -- coding: utf-8 --
"""
DuckDB 执行引擎

提供 SQL 执行、结果转换、性能优化功能
"""
from typing import Dict, List, Optional, Any
import pandas as pd

from apps.core.logger import alert_logger as logger
from apps.alerts.aggregation_v2.db_engine.connection import DuckDBConnectionPool
from apps.alerts.aggregation_v2.utils.metrics import PerformanceMonitor


class DuckDBEngine:
    """
    DuckDB 执行引擎
    
    职责：
    1. 执行渲染后的 SQL 查询
    2. DataFrame 与 DuckDB 的双向转换
    3. 查询性能监控
    4. 错误处理和日志记录
    """

    @classmethod
    def execute_query(
            cls,
            sql: str,
            events_df: pd.DataFrame,
            params: Optional[Dict[str, Any]] = None
    ) -> pd.DataFrame:
        """
        执行 SQL 查询并返回结果
        
        Args:
            sql: 要执行的 SQL 语句
            events_df: 事件数据 DataFrame（将注册为 'events' 表）
            params: SQL 参数（用于参数化查询，可选）
            
        Returns:
            查询结果 DataFrame
            
        Examples:
            >>> events_df = pd.DataFrame([...])
            >>> sql = "SELECT * FROM events WHERE level >= 3"
            >>> result = DuckDBEngine.execute_query(sql, events_df)
        """
        if events_df.empty:
            logger.warning("事件 DataFrame 为空，跳过查询")
            return pd.DataFrame()

        with PerformanceMonitor("DuckDB 查询执行") as pm:
            try:
                with DuckDBConnectionPool.connection_context() as conn:
                    # 注册 DataFrame 为临时表
                    conn.register('events', events_df)

                    # 执行查询
                    if params:
                        result_df = conn.execute(sql, params).df()
                    else:
                        result_df = conn.execute(sql).df()

                    # 取消注册（释放内存）
                    conn.unregister('events')

                    logger.info(
                        f"DuckDB 查询完成: 输入={len(events_df)} 行, "
                        f"输出={len(result_df)} 行, 耗时={pm.elapsed_ms:.2f}ms"
                    )

                    return result_df

            except Exception as e:
                logger.error(f"DuckDB 查询失败: {e}\nSQL:\n{sql}")
                cls._log_debug_info(events_df, sql)
                raise

    @classmethod
    def execute_query_batch(
            cls,
            sql_list: List[str],
            events_df: pd.DataFrame
    ) -> List[pd.DataFrame]:
        """
        批量执行多个 SQL 查询（复用同一个 DataFrame 注册）
        
        Args:
            sql_list: SQL 语句列表
            events_df: 事件数据 DataFrame
            
        Returns:
            结果 DataFrame 列表
        """
        if events_df.empty:
            logger.warning("事件 DataFrame 为空，跳过批量查询")
            return [pd.DataFrame()] * len(sql_list)

        results = []

        with PerformanceMonitor("DuckDB 批量查询") as pm:
            try:
                with DuckDBConnectionPool.connection_context() as conn:
                    # 一次注册
                    conn.register('events', events_df)

                    # 执行所有查询
                    for i, sql in enumerate(sql_list):
                        try:
                            result_df = conn.execute(sql).df()
                            results.append(result_df)
                            logger.debug(f"批量查询 {i + 1}/{len(sql_list)} 完成: {len(result_df)} 行")
                        except Exception as e:
                            logger.error(f"批量查询 {i + 1} 失败: {e}\nSQL:\n{sql}")
                            results.append(pd.DataFrame())

                    # 取消注册
                    conn.unregister('events')

                    logger.info(
                        f"DuckDB 批量查询完成: {len(sql_list)} 个查询, "
                        f"耗时={pm.elapsed_ms:.2f}ms"
                    )

                    return results

            except Exception as e:
                logger.error(f"DuckDB 批量查询失败: {e}")
                raise

    @classmethod
    def validate_sql(cls, sql: str) -> bool:
        """
        验证 SQL 语法（不执行）
        
        Args:
            sql: 要验证的 SQL 语句
            
        Returns:
            True=语法正确，False=语法错误
        """
        try:
            with DuckDBConnectionPool.connection_context() as conn:
                # 使用 EXPLAIN 验证语法
                conn.execute(f"EXPLAIN {sql}")
                return True
        except Exception as e:
            logger.error(f"SQL 语法错误: {e}\nSQL:\n{sql}")
            return False

    @classmethod
    def get_query_plan(cls, sql: str, events_df: pd.DataFrame) -> str:
        """
        获取查询执行计划（用于性能调优）
        
        Args:
            sql: SQL 语句
            events_df: 事件数据 DataFrame
            
        Returns:
            执行计划文本
        """
        try:
            with DuckDBConnectionPool.connection_context() as conn:
                conn.register('events', events_df)

                # 获取执行计划
                plan = conn.execute(f"EXPLAIN {sql}").fetchall()

                conn.unregister('events')

                # 格式化输出
                plan_text = "\n".join([str(row[1]) for row in plan])
                return plan_text

        except Exception as e:
            logger.error(f"获取执行计划失败: {e}")
            return f"ERROR: {e}"

    @classmethod
    def _log_debug_info(cls, events_df: pd.DataFrame, sql: str) -> None:
        """
        记录调试信息（查询失败时）
        
        Args:
            events_df: 事件数据 DataFrame
            sql: 失败的 SQL 语句
        """
        logger.debug("=== DuckDB 调试信息 ===")
        logger.debug(f"DataFrame 形状: {events_df.shape}")
        logger.debug(f"DataFrame 列: {events_df.columns.tolist()}")
        logger.debug(f"DataFrame 数据类型:\n{events_df.dtypes}")
        logger.debug(f"DataFrame 前5行:\n{events_df.head()}")
        logger.debug(f"失败的 SQL:\n{sql}")
        logger.debug("=====================")

    @classmethod
    def optimize_dataframe(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        优化 DataFrame 内存占用（类型转换）
        
        Args:
            df: 原始 DataFrame
            
        Returns:
            优化后的 DataFrame
        """
        if df.empty:
            return df

        optimized_df = df.copy()

        # 优化整数类型
        for col in optimized_df.select_dtypes(include=['int64']).columns:
            col_min = optimized_df[col].min()
            col_max = optimized_df[col].max()

            if col_min >= 0:
                # 无符号整数
                if col_max < 255:
                    optimized_df[col] = optimized_df[col].astype('uint8')
                elif col_max < 65535:
                    optimized_df[col] = optimized_df[col].astype('uint16')
                elif col_max < 4294967295:
                    optimized_df[col] = optimized_df[col].astype('uint32')
            else:
                # 有符号整数
                if col_min > -128 and col_max < 127:
                    optimized_df[col] = optimized_df[col].astype('int8')
                elif col_min > -32768 and col_max < 32767:
                    optimized_df[col] = optimized_df[col].astype('int16')
                elif col_min > -2147483648 and col_max < 2147483647:
                    optimized_df[col] = optimized_df[col].astype('int32')

        # 优化浮点类型
        for col in optimized_df.select_dtypes(include=['float64']).columns:
            optimized_df[col] = optimized_df[col].astype('float32')

        # 优化对象类型（转为 category）
        for col in optimized_df.select_dtypes(include=['object']).columns:
            num_unique = optimized_df[col].nunique()
            num_total = len(optimized_df[col])

            # 如果唯一值 < 50% 的总行数，转为 category
            if num_unique / num_total < 0.5:
                optimized_df[col] = optimized_df[col].astype('category')

        original_size = df.memory_usage(deep=True).sum() / 1024 / 1024
        optimized_size = optimized_df.memory_usage(deep=True).sum() / 1024 / 1024

        logger.debug(
            f"DataFrame 内存优化: {original_size:.2f}MB -> {optimized_size:.2f}MB "
            f"(节省 {(1 - optimized_size / original_size) * 100:.1f}%)"
        )

        return optimized_df
