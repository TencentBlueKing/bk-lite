# -- coding: utf-8 --
"""
会话窗口处理器

处理基于事件间隔的会话窗口聚合
"""
from typing import List
import pandas as pd

from apps.alerts.models import Alert
from apps.alerts.aggregation_v2.processors.base import BaseWindowProcessor
from apps.alerts.aggregation_v2.query.strategy import EventQueryStrategy
from apps.alerts.aggregation_v2.templates.engine import TemplateEngine
from apps.alerts.aggregation_v2.db_engine.engine import DuckDBEngine
from apps.alerts.aggregation_v2.utils.metrics import PerformanceMonitor
from apps.alerts.aggregation_v2.alert_builder.builder import AlertBuilder
from apps.core.logger import alert_logger as logger


class SessionWindowProcessor(BaseWindowProcessor):
    """
    会话窗口处理器
    
    特点：
    - 基于事件间隔动态确定窗口边界
    - 使用 LAG() + SUM() OVER() 实现会话分组
    - 支持最大窗口限制防止无限扩展
    """
    
    def process(self) -> List[Alert]:
        """处理会话窗口聚合"""
        self._log_processing_start()
        
        with PerformanceMonitor("会话窗口处理") as pm:
            # 1. 查询事件
            events_df = EventQueryStrategy.get_events_for_correlation_rule(
                self.correlation_rule
            )
            
            if events_df.empty:
                logger.info(f"规则 {self.rule_name} 没有待处理事件")
                return []
            
            # 2. 渲染 SQL（使用 LAG + SUM 实现会话分组）
            template_engine = TemplateEngine()
            sql = template_engine.render_sql(self.correlation_rule)
            
            logger.debug(f"会话窗口 SQL:\n{sql}")
            
            # 3. 执行 DuckDB 查询
            result_df = DuckDBEngine.execute_query(sql, events_df)
            
            # 4. 验证结果
            if not self._validate_result(result_df):
                return []
            
            # 5. 检查会话时长（防止异常长会话）
            result_df = self._validate_session_duration(result_df)
            
            # 6. 构建告警
            alerts = self._build_alerts(result_df)
            
            self._log_processing_end(len(alerts), pm.elapsed_ms)
            
            return alerts
    
    def _validate_session_duration(self, result_df: pd.DataFrame) -> pd.DataFrame:
        """
        验证会话时长
        
        过滤掉异常长的会话（可能是数据异常或配置错误）
        """
        if result_df.empty:
            return result_df
        
        # 计算会话时长
        result_df['session_duration'] = (
            pd.to_datetime(result_df['last_event_time']) -
            pd.to_datetime(result_df['first_event_time'])
        ).dt.total_seconds()
        
        # 获取最大窗口限制
        max_duration = None
        if self.correlation_rule.max_window_size:
            from apps.alerts.aggregation_v2.utils.time_utils import TimeUtils
            max_duration = TimeUtils.parse_time_str_to_seconds(
                self.correlation_rule.max_window_size
            )
        
        if max_duration:
            # 过滤超时会话
            original_count = len(result_df)
            result_df = result_df[result_df['session_duration'] <= max_duration]
            
            if len(result_df) < original_count:
                logger.warning(
                    f"会话窗口超时过滤: {original_count} -> {len(result_df)} "
                    f"(最大={max_duration}秒)"
                )
        
        return result_df
    
    def _build_alerts(self, result_df: pd.DataFrame) -> List[Alert]:
        """构建告警对象"""
        logger.info(f"会话窗口聚合结果: {len(result_df)} 个会话")
        
        # 使用 AlertBuilder 构建告警
        created_alerts, updated_alerts = AlertBuilder.build_from_aggregation_result(
            result_df=result_df,
            correlation_rule=self.correlation_rule,
            window_type='session'
        )
        
        # 合并返回所有告警
        all_alerts = created_alerts + updated_alerts
        return all_alerts
