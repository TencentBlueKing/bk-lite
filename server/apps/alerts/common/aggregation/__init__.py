# -- coding: utf-8 --
# @File: __init__.py
# @Time: 2025/9/16 10:40
# @Author: windyzhao

"""
DuckDB聚合告警模块

提供基于DuckDB的高性能事件聚合告警功能，支持三种窗口类型：
- 滑动窗口 (Sliding Window): 适用于实时监控
- 固定窗口 (Fixed Window): 适用于定期统计  
- 会话窗口 (Session Window): 适用于故障跟踪

主要组件：
- DuckDBEngine: DuckDB数据库引擎封装
- DuckDBSQL: SQL模板生成器
- AggregationController: 聚合控制器

使用示例：
    from apps.alerts.common.aggregation import AggregationController
    
    controller = AggregationController()
    result = controller.execute_aggregation_by_rule(rule_id=1)
"""

from .duckdb_engine import DuckDBEngine

# 查找 DuckDBEngine 相关配置文件
# 通常位于同目录下的其他模块中

__version__ = "1.0.0"
__author__ = "windyzhao"

__all__ = [
    'DuckDBEngine',
]