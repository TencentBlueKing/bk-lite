# -- coding: utf-8 --
"""
DuckDB 引擎模块

提供高性能的内存数据库聚合计算
"""

from .engine import DuckDBEngine
from .connection import DuckDBConnectionPool

__all__ = [
    'DuckDBEngine',
    'DuckDBConnectionPool'
]
