# -- coding: utf-8 --
"""
固定窗口处理器

处理固定时间窗口的事件聚合
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


class FixedWindowProcessor(BaseWindowProcessor):
    """
    固定窗口处理器
    
    特点：
    - 窗口边界固定（按时间对齐）
    - 窗口不重叠
    - 适合周期性统计
    """
    
    def process(self) -> List[Alert]:
        """处理固定窗口聚合"""
        self._log_processing_start()
        
        with PerformanceMonitor("固定窗口处理") as pm:
            # 1. 查询事件
            events_df = EventQueryStrategy.get_events_for_correlation_rule(
                self.correlation_rule
            )
            
            if events_df.empty:
                logger.info(f"规则 {self.rule_name} 没有待处理事件")
                return []
            
            # 2. 渲染 SQL
            template_engine = TemplateEngine()
            sql = template_engine.render_sql(self.correlation_rule)
            
            logger.debug(f"固定窗口 SQL:\n{sql}")
            
            # 3. 执行 DuckDB 查询
            result_df = DuckDBEngine.execute_query(sql, events_df)
            
            # 4. 验证结果
            if not self._validate_result(result_df):
                return []
            
            # 5. 构建告警（暂时返回空列表，待实现 AlertBuilder）
            alerts = self._build_alerts(result_df)
            
            self._log_processing_end(len(alerts), pm.elapsed_ms)
            
            return alerts
    
    def _build_alerts(self, result_df: pd.DataFrame) -> List[Alert]:
        """
        构建告警对象
        """
        logger.info(f"固定窗口聚合结果: {len(result_df)} 个窗口")
        
        # 使用 AlertBuilder 构建告警
        created_alerts, updated_alerts = AlertBuilder.build_from_aggregation_result(
            result_df=result_df,
            correlation_rule=self.correlation_rule,
            window_type='fixed'
        )
        
        # 合并返回所有告警
        all_alerts = created_alerts + updated_alerts
        return all_alerts
