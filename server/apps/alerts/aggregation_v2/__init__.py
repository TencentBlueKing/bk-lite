# -- coding: utf-8 --
"""
告警聚合系统 V2

全新设计的统一告警聚合引擎，支持：
- 3 种窗口类型：固定窗口、滑动窗口、会话窗口
- 3 种策略类型：阈值告警、复合条件、频率告警
- SQL 原生窗口计算（基于 DuckDB）
- 智能查询优化和缓存
- 高性能增量处理

架构设计：
- query/: 查询策略和优化
- db_engine/: DuckDB 引擎和 SQL 执行
- templates/: Jinja2 模板和 SQL 生成
- rules/: 规则转换和适配
- processors/: 窗口处理器
- alert_builder/: 告警构建和格式化
- state/: 状态管理和缓存
- tasks/: Celery 异步任务
- utils/: 工具函数

作者: windyzhao
"""

__version__ = "2.0.0"
__author__ = "windyzhao"

# 公共接口（按需暴露）
# from .query.strategy import EventQueryStrategy
# from .processors.factory import WindowProcessorFactory
# from .db_engine.engine import DuckDBEngine
