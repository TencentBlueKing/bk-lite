# -- coding: utf-8 --
"""
聚合系统 V2 配置文件

集中管理所有配置项，支持环境变量覆盖
"""
import os
from typing import Dict, Any


class AggregationV2Config:
    """聚合系统 V2 全局配置"""
    
    # ========== 功能开关 ==========
    
    # 启用查询缓存
    ENABLE_QUERY_CACHE: bool = os.getenv('AGG_V2_ENABLE_QUERY_CACHE', 'true').lower() == 'true'
    
    # 启用窗口处理追踪（防止重复处理）
    ENABLE_WINDOW_TRACKING: bool = os.getenv('AGG_V2_ENABLE_WINDOW_TRACKING', 'true').lower() == 'true'
    
    # 启用滑动窗口增量计算
    ENABLE_INCREMENTAL_SLIDING: bool = os.getenv('AGG_V2_ENABLE_INCREMENTAL_SLIDING', 'false').lower() == 'true'
    
    # 启用性能监控
    ENABLE_PERFORMANCE_MONITORING: bool = os.getenv('AGG_V2_ENABLE_PERFORMANCE_MONITORING', 'true').lower() == 'true'
    
    # 启用智能调度（滑动窗口空跑检测）
    ENABLE_SMART_SCHEDULING: bool = os.getenv('AGG_V2_ENABLE_SMART_SCHEDULING', 'true').lower() == 'true'
    
    # ========== DuckDB 配置 ==========
    
    # 内存限制
    DUCKDB_MEMORY_LIMIT: str = os.getenv('AGG_V2_DUCKDB_MEMORY_LIMIT', '512MB')
    
    # 线程数
    DUCKDB_THREADS: int = int(os.getenv('AGG_V2_DUCKDB_THREADS', '2'))
    
    # 最大内存
    DUCKDB_MAX_MEMORY: str = os.getenv('AGG_V2_DUCKDB_MAX_MEMORY', '1GB')
    
    # 启用查询优化
    DUCKDB_ENABLE_OPTIMIZER: bool = True
    
    # ========== 查询配置 ==========
    
    # 查询缓存 TTL（秒）
    QUERY_CACHE_TTL: int = int(os.getenv('AGG_V2_QUERY_CACHE_TTL', '300'))
    
    # 查询超时时间（秒）
    QUERY_TIMEOUT: int = int(os.getenv('AGG_V2_QUERY_TIMEOUT', '30'))
    
    # 最大查询结果数
    MAX_QUERY_RESULTS: int = int(os.getenv('AGG_V2_MAX_QUERY_RESULTS', '10000'))
    
    # ========== 窗口配置 ==========
    
    # 固定窗口：缓冲时间倍数
    FIXED_WINDOW_BUFFER_MULTIPLIER: float = float(os.getenv('AGG_V2_FIXED_BUFFER_MULTIPLIER', '2.0'))
    
    # 滑动窗口：状态缓存 TTL（秒）
    SLIDING_WINDOW_STATE_TTL: int = int(os.getenv('AGG_V2_SLIDING_STATE_TTL', '3600'))
    
    # 会话窗口：默认最大持续时间（秒）
    SESSION_DEFAULT_MAX_DURATION: int = int(os.getenv('AGG_V2_SESSION_MAX_DURATION', '7200'))
    
    # 会话窗口：默认最大事件数
    SESSION_DEFAULT_MAX_EVENTS: int = int(os.getenv('AGG_V2_SESSION_MAX_EVENTS', '1000'))
    
    # ========== Redis 配置 ==========
    
    # Redis 键前缀
    REDIS_KEY_PREFIX: str = os.getenv('AGG_V2_REDIS_PREFIX', 'alerts:agg_v2:')
    
    # 窗口状态键模板
    WINDOW_STATE_KEY_TEMPLATE: str = REDIS_KEY_PREFIX + 'window_state:{rule_id}:{window_id}'
    
    # 已处理窗口键模板
    PROCESSED_WINDOW_KEY_TEMPLATE: str = REDIS_KEY_PREFIX + 'processed:{rule_id}:{window_id}'
    
    # 上次执行时间键模板
    LAST_EXECUTION_KEY_TEMPLATE: str = REDIS_KEY_PREFIX + 'last_exec:{rule_id}'
    
    # ========== 性能配置 ==========
    
    # 批量操作大小
    BATCH_SIZE: int = int(os.getenv('AGG_V2_BATCH_SIZE', '1000'))
    
    # 并发处理规则数
    MAX_CONCURRENT_RULES: int = int(os.getenv('AGG_V2_MAX_CONCURRENT_RULES', '10'))
    
    # SQL 执行超时（秒）
    SQL_EXECUTION_TIMEOUT: int = int(os.getenv('AGG_V2_SQL_TIMEOUT', '60'))
    
    # ========== 日志配置 ==========
    
    # 日志级别
    LOG_LEVEL: str = os.getenv('AGG_V2_LOG_LEVEL', 'INFO')
    
    # 启用详细日志
    VERBOSE_LOGGING: bool = os.getenv('AGG_V2_VERBOSE_LOGGING', 'false').lower() == 'true'
    
    # SQL 日志（记录生成的 SQL）
    LOG_SQL: bool = os.getenv('AGG_V2_LOG_SQL', 'false').lower() == 'true'
    
    # ========== 告警配置 ==========
    
    # 告警去重窗口（秒）
    ALERT_DEDUP_WINDOW: int = int(os.getenv('AGG_V2_ALERT_DEDUP_WINDOW', '60'))
    
    # 最大告警数（单次处理）
    MAX_ALERTS_PER_EXECUTION: int = int(os.getenv('AGG_V2_MAX_ALERTS', '1000'))
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典"""
        return {
            key: getattr(cls, key)
            for key in dir(cls)
            if key.isupper() and not key.startswith('_')
        }
    
    @classmethod
    def validate(cls) -> bool:
        """验证配置有效性"""
        try:
            # 验证内存配置
            assert cls.DUCKDB_THREADS > 0, "DUCKDB_THREADS 必须大于 0"
            assert cls.BATCH_SIZE > 0, "BATCH_SIZE 必须大于 0"
            
            # 验证时间配置
            assert cls.QUERY_TIMEOUT > 0, "QUERY_TIMEOUT 必须大于 0"
            assert cls.SQL_EXECUTION_TIMEOUT > 0, "SQL_EXECUTION_TIMEOUT 必须大于 0"
            
            return True
        except AssertionError as e:
            from apps.core.logger import alert_logger
            alert_logger.error(f"配置验证失败: {e}")
            return False
    
    @classmethod
    def print_config(cls):
        """打印当前配置"""
        from apps.core.logger import alert_logger
        alert_logger.info("=" * 60)
        alert_logger.info("聚合系统 V2 配置")
        alert_logger.info("=" * 60)
        for key, value in cls.to_dict().items():
            alert_logger.info(f"{key}: {value}")
        alert_logger.info("=" * 60)


# 配置验证
if not AggregationV2Config.validate():
    raise ValueError("聚合系统 V2 配置无效，请检查环境变量")
