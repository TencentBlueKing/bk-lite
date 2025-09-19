# -- coding: utf-8 --
# @File: duckdb_sql.py
# @Time: 2025/9/15 16:53
# @Author: windyzhao

"""
DuckDB SQL 语句生成器模块

提供三种窗口类型的SQL查询模板：

1. 滑动窗口 (Sliding Window): 
   - 特点：每次查询最近N分钟的数据
   - 问题：在1分钟执行周期下，同一事件可能被重复处理多次
   - 适用：实时监控，允许重复检测以确保快速响应

2. 固定窗口 (Fixed Window): 
   - 特点：按时间对齐分割，每个事件只属于一个时间段
   - 优势：避免重复处理，每个事件只生成一次告警
   - 适用：定期统计，避免重复告警

3. 会话窗口 (Session Window): 
   - 特点：基于事件间隔动态调整窗口大小
   - 用途：检测"活动停止"状态，如故障未恢复、无人处理等
   - 适用：SLA监控，故障跟踪

关键区别：
- 滑动窗口：查询基准是"当前时间"，可能重复处理
- 固定窗口：查询基准是"时间对齐边界"，避免重复
- 会话窗口：查询基准是"事件间隔"，动态窗口

使用示例:
    # 滑动窗口 - 实时监控，可能重复告警
    query = DuckDBSQL.generate_sliding_window_query(
        table='alerts_event',
        time_column='start_time', 
        window_size=10,
        slide_interval=1
    )
    
    # 固定窗口 - 定期统计，避免重复
    query = DuckDBSQL.generate_fixed_window_query(
        table='alerts_event',
        time_column='start_time',
        window_size=15
    )
    
    # 会话窗口 - 故障跟踪
    query = DuckDBSQL.generate_session_window_query(
        table='alerts_event',
        time_column='start_time',
        session_gap=5,
        timeout=30
    )
"""


class DuckDBSQL:
    """
    DuckDB SQL 语句生成器
    """

    @staticmethod
    def generate_sliding_window_query(table: str, time_column: str, window_size: int, slide_interval: int,
                                      fields: str = "*") -> str:
        """
        生成滑动窗口聚合的SQL查询语句
        
        注意：在1分钟执行周期下，真正的滑动窗口需要考虑历史窗口的重叠数据
        此实现通过回看更长时间范围来模拟滑动效果
        
        Args:
            table: 事件数据表名
            fields: 查询的字段 默认 '*'
            time_column: 时间戳列名
            window_size: 窗口大小（分钟）
            slide_interval: 滑动间隔（分钟，通常为1分钟）
        Returns:
            SQL查询字符串
        """
        query = f"""
        WITH sliding_window AS (
            SELECT 
                event_id,
                title,
                description,
                level,
                {time_column},
                resource_id,
                resource_type,
                resource_name,
                item,
                source_id,
                labels,
                status,
                action,
                value,
                rule_id,
                -- 使用 ROW_NUMBER 为窗口内的事件排序
                ROW_NUMBER() OVER (
                    PARTITION BY resource_id, item, level 
                    ORDER BY {time_column} DESC
                ) as rn
            FROM {table}
            WHERE {time_column} >= NOW() - INTERVAL '{window_size} minutes'
              AND {time_column} < NOW() - INTERVAL '{slide_interval - 1} minutes'
              AND action = 'created'
              AND status = 'received'
        ),
        aggregated_events AS (
            SELECT 
                CONCAT('SW-', DATE_TRUNC('minute', MIN({time_column})), '-', 
                       COALESCE(resource_id, 'unknown'), '-', 
                       COALESCE(item, 'unknown')) as window_id,
                MIN({time_column}) as window_start,
                MAX({time_column}) as window_end,
                resource_id,
                resource_type,
                resource_name,
                item,
                level,
                COUNT(*) as event_count,
                ARRAY_AGG(event_id ORDER BY {time_column}) as event_ids,
                ARRAY_AGG(title ORDER BY {time_column}) as event_titles,
                FIRST(description ORDER BY {time_column}) as first_description,
                LAST(description ORDER BY {time_column}) as last_description,
                -- 聚合标签信息
                REDUCE(ARRAY_AGG(labels), CAST(NULL AS JSON), (acc, x) -> 
                    CASE WHEN acc IS NULL THEN x ELSE JSON_MERGE_PATCH(acc, x) END
                ) as merged_labels,
                -- 聚合数值
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                STDDEV(value) as stddev_value
            FROM sliding_window
            GROUP BY resource_id, resource_type, resource_name, item, level
            HAVING COUNT(*) >= 1  -- 可以通过参数动态控制阈值
        )
        SELECT 
            window_id,
            window_start,
            window_end,
            resource_id,
            resource_type,
            resource_name,
            item,
            level,
            event_count,
            event_ids,
            event_titles,
            first_description,
            last_description,
            merged_labels,
            avg_value,
            min_value,
            max_value,
            stddev_value,
            'sliding' as window_type,
            {window_size} as window_size_minutes,
            {slide_interval} as slide_interval_minutes
        FROM aggregated_events
        ORDER BY window_start DESC, event_count DESC
        """
        return query

    @staticmethod
    def generate_fixed_window_query(table: str, time_column: str, window_size: int, fields: str = "*") -> str:
        """
        生成固定窗口聚合的SQL查询语句
        
        固定窗口特点：
        - 窗口边界严格按时间对齐（如每5分钟、每15分钟）
        - 只在窗口完全结束后才处理该窗口的数据
        - 每个时间点的事件只属于一个窗口
        
        Args:
            table: 事件数据表名
            time_column: 时间戳列名
            fields: 查询的字段 默认 '*'
            window_size: 窗口大小（分钟）
        Returns:
            SQL查询字符串
        """
        query = f"""
        WITH fixed_window_boundaries AS (
            -- 计算固定窗口边界，确保时间对齐
            SELECT 
                DATE_TRUNC('minute', 
                    DATE_SUB(NOW(), INTERVAL MOD(EXTRACT(MINUTE FROM NOW()), {window_size}) MINUTE)
                ) as current_window_end,
                DATE_TRUNC('minute', 
                    DATE_SUB(NOW(), INTERVAL ({window_size} + MOD(EXTRACT(MINUTE FROM NOW()), {window_size})) MINUTE)
                ) as current_window_start
        ),
        windowed_events AS (
            SELECT 
                e.*,
                -- 计算每个事件属于哪个窗口
                DATE_TRUNC('minute', 
                    DATE_SUB(e.{time_column}, 
                        INTERVAL MOD(EXTRACT(MINUTE FROM e.{time_column}), {window_size}) MINUTE)
                ) as window_start,
                DATE_TRUNC('minute', 
                    DATE_ADD(
                        DATE_SUB(e.{time_column}, 
                            INTERVAL MOD(EXTRACT(MINUTE FROM e.{time_column}), {window_size}) MINUTE),
                        INTERVAL {window_size} MINUTE
                    )
                ) as window_end
            FROM {table} e
            CROSS JOIN fixed_window_boundaries fwb
            WHERE e.{time_column} >= fwb.current_window_start
              AND e.{time_column} < fwb.current_window_end  -- 只处理完整的窗口
              AND e.action = 'created'
              AND e.status = 'received'
        ),
        aggregated_events AS (
            SELECT 
                CONCAT('FW-', window_start, '-', 
                       COALESCE(resource_id, 'unknown'), '-', 
                       COALESCE(item, 'unknown')) as window_id,
                window_start,
                window_end,
                resource_id,
                resource_type,
                resource_name,
                item,
                level,
                COUNT(*) as event_count,
                ARRAY_AGG(event_id ORDER BY {time_column}) as event_ids,
                ARRAY_AGG(title ORDER BY {time_column}) as event_titles,
                FIRST(description ORDER BY {time_column}) as first_description,
                LAST(description ORDER BY {time_column}) as last_description,
                MIN({time_column}) as first_event_time,
                MAX({time_column}) as last_event_time,
                -- 聚合标签信息
                REDUCE(ARRAY_AGG(labels), CAST(NULL AS JSON), (acc, x) -> 
                    CASE WHEN acc IS NULL THEN x ELSE JSON_MERGE_PATCH(acc, x) END
                ) as merged_labels,
                -- 聚合数值
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                STDDEV(value) as stddev_value,
                -- 事件密度计算
                COUNT(*) / {window_size}.0 as events_per_minute
            FROM windowed_events
            GROUP BY window_start, window_end, resource_id, resource_type, resource_name, item, level
            HAVING COUNT(*) >= 1  -- 可以通过参数动态控制阈值
        )
        SELECT 
            window_id,
            window_start,
            window_end,
            resource_id,
            resource_type,
            resource_name,
            item,
            level,
            event_count,
            event_ids,
            event_titles,
            first_description,
            last_description,
            first_event_time,
            last_event_time,
            merged_labels,
            avg_value,
            min_value,
            max_value,
            stddev_value,
            events_per_minute,
            'fixed' as window_type,
            {window_size} as window_size_minutes,
            EXTRACT(EPOCH FROM (window_end - window_start)) / 60 as actual_window_duration_minutes
        FROM aggregated_events
        ORDER BY window_start DESC, event_count DESC
        """
        return query

    @staticmethod
    def generate_session_window_query(table: str, time_column: str, session_gap: int, timeout: int) -> str:
        """
        生成会话窗口聚合的SQL查询语句
        
        会话窗口特点：
        - 基于事件间隔动态调整窗口大小
        - 当事件间隔超过session_gap时，当前会话结束，新会话开始
        - 会话超时机制：超过timeout时间没有新事件时强制关闭会话
        
        Args:
            table: 事件数据表名
            time_column: 时间戳列名
            session_gap: 会话间隔（分钟），超过此间隔开始新会话
            timeout: 查询超时时间（分钟），会话最大持续时间
        Returns:
            SQL查询字符串
        """
        query = f"""
        WITH session_events AS (
            SELECT 
                *,
                -- 计算与前一个事件的时间间隔
                EXTRACT(EPOCH FROM ({time_column} - LAG({time_column}) OVER (
                    PARTITION BY resource_id, item, level 
                    ORDER BY {time_column}
                ))) / 60.0 as gap_minutes,
                -- 为每个事件分组标识符
                ROW_NUMBER() OVER (
                    PARTITION BY resource_id, item, level 
                    ORDER BY {time_column}
                ) as event_sequence
            FROM {table}
            WHERE {time_column} >= NOW() - INTERVAL '{timeout} minutes'
              AND action = 'created'
              AND status = 'received'
        ),
        session_boundaries AS (
            SELECT 
                *,
                -- 标识会话边界：第一个事件或间隔超过session_gap的事件
                CASE 
                    WHEN event_sequence = 1 THEN 1
                    WHEN gap_minutes > {session_gap} THEN 1
                    ELSE 0
                END as is_session_start
            FROM session_events
        ),
        session_groups AS (
            SELECT 
                *,
                -- 为每个会话分配唯一的会话ID
                SUM(is_session_start) OVER (
                    PARTITION BY resource_id, item, level 
                    ORDER BY {time_column} 
                    ROWS UNBOUNDED PRECEDING
                ) as session_group_id
            FROM session_boundaries
        ),
        session_windows AS (
            SELECT 
                resource_id,
                resource_type, 
                resource_name,
                item,
                level,
                session_group_id,
                MIN({time_column}) as session_start,
                MAX({time_column}) as session_end,
                COUNT(*) as event_count,
                ARRAY_AGG(event_id ORDER BY {time_column}) as event_ids,
                ARRAY_AGG(title ORDER BY {time_column}) as event_titles,
                FIRST(description ORDER BY {time_column}) as first_description,
                LAST(description ORDER BY {time_column}) as last_description,
                -- 聚合标签信息
                REDUCE(ARRAY_AGG(labels), CAST(NULL AS JSON), (acc, x) -> 
                    CASE WHEN acc IS NULL THEN x ELSE JSON_MERGE_PATCH(acc, x) END
                ) as merged_labels,
                -- 聚合数值
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                STDDEV(value) as stddev_value,
                -- 会话持续时间
                EXTRACT(EPOCH FROM (MAX({time_column}) - MIN({time_column}))) / 60.0 as duration_minutes,
                -- 会话状态判断
                CASE 
                    WHEN EXTRACT(EPOCH FROM (NOW() - MAX({time_column}))) / 60.0 > {session_gap} THEN 'closed'
                    WHEN EXTRACT(EPOCH FROM (MAX({time_column}) - MIN({time_column}))) / 60.0 > {timeout} THEN 'timeout'
                    ELSE 'active'
                END as session_status
            FROM session_groups
            GROUP BY resource_id, resource_type, resource_name, item, level, session_group_id
        ),
        aggregated_sessions AS (
            SELECT 
                CONCAT('SW-', session_start, '-', resource_id, '-', item, '-', session_group_id) as window_id,
                session_start as window_start,
                session_end as window_end,
                resource_id,
                resource_type,
                resource_name,
                item,
                level,
                event_count,
                event_ids,
                event_titles,
                first_description,
                last_description,
                merged_labels,
                avg_value,
                min_value,
                max_value,
                stddev_value,
                duration_minutes,
                session_status,
                session_group_id,
                -- 事件频率计算
                CASE 
                    WHEN duration_minutes > 0 THEN event_count / duration_minutes
                    ELSE event_count
                END as events_per_minute
            FROM session_windows
            WHERE event_count >= 1  -- 可以通过参数动态控制阈值
        )
        SELECT 
            window_id,
            window_start,
            window_end,
            resource_id,
            resource_type,
            resource_name,
            item,
            level,
            event_count,
            event_ids,
            event_titles,
            first_description,
            last_description,
            merged_labels,
            avg_value,
            min_value,
            max_value,
            stddev_value,
            duration_minutes,
            session_status,
            session_group_id,
            events_per_minute,
            'session' as window_type,
            {session_gap} as session_gap_minutes,
            {timeout} as timeout_minutes
        FROM aggregated_sessions
        ORDER BY 
            CASE session_status 
                WHEN 'active' THEN 1 
                WHEN 'timeout' THEN 2 
                WHEN 'closed' THEN 3 
            END,
            window_start DESC, 
            event_count DESC
        """
        return query

    @classmethod
    def get_query_template(cls, window_type: str, **kwargs) -> str:
        """
        根据窗口类型获取对应的查询模板
        Args:
            window_type: 窗口类型 ('sliding', 'fixed', 'session')
            **kwargs: 查询参数
        Returns:
            SQL查询字符串
        Raises:
            ValueError: 不支持的窗口类型
        """
        table = kwargs.get('table', 'alerts_event')
        time_column = kwargs.get('time_column', 'start_time')
        fields = kwargs.get('fields', '*')

        if window_type == 'sliding':
            window_size = kwargs.get('window_size', 10)
            slide_interval = kwargs.get('slide_interval', 1)
            return cls.generate_sliding_window_query(table, time_column, window_size, slide_interval, fields)

        elif window_type == 'fixed':
            window_size = kwargs.get('window_size', 10)
            return cls.generate_fixed_window_query(table, time_column, window_size, fields)

        elif window_type == 'session':
            session_gap = kwargs.get('session_gap', 5)
            timeout = kwargs.get('timeout', 30)
            return cls.generate_session_window_query(table, time_column, session_gap, timeout)

        else:
            raise ValueError(f"不支持的窗口类型: {window_type}")

    @staticmethod
    def explain_window_behavior_in_1min_cycle() -> dict:
        """
        解释三种窗口类型在1分钟执行周期下的行为差异
        
        Returns:
            包含三种窗口类型行为说明的字典
        """
        return {
            "execution_cycle": "1分钟",
            "window_types": {
                "sliding": {
                    "behavior": "滑动窗口 - 连续覆盖",
                    "description": "每分钟产生一个新窗口，窗口之间有重叠",
                    "example": "10分钟窗口：[0-10], [1-11], [2-12]...",
                    "data_coverage": "连续且重叠",
                    "use_case": "实时监控，需要连续观察趋势",
                    "pros": "数据覆盖完整，能捕获所有变化",
                    "cons": "可能产生重复告警，需要去重处理"
                },
                "fixed": {
                    "behavior": "固定窗口 - 定期对齐",
                    "description": "只在窗口大小的倍数时刻执行，窗口无重叠",
                    "example": "10分钟窗口：[0-10], [10-20], [20-30]...",
                    "data_coverage": "完整且不重叠",
                    "use_case": "定期统计，批量处理",
                    "pros": "数据不重复，处理清晰",
                    "cons": "可能错过窗口边界附近的重要事件"
                },
                "session": {
                    "behavior": "会话窗口 - 活动驱动",
                    "description": "基于事件活动检测，窗口大小动态变化",
                    "example": "5分钟间隔：当连续5分钟无事件时关闭会话",
                    "data_coverage": "基于业务逻辑动态调整",
                    "use_case": "故障处理跟踪，用户行为分析",
                    "pros": "符合业务逻辑，能准确反映活动状态",
                    "cons": "逻辑复杂，需要状态管理"
                }
            },
            "recommendations": {
                "real_time_alerting": "使用滑动窗口，但需要在告警去重方面做好处理",
                "periodic_reports": "使用固定窗口，确保数据统计的准确性",
                "incident_tracking": "使用会话窗口，跟踪问题处理的完整生命周期"
            }
        }
