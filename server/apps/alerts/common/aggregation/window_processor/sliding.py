# -- coding: utf-8 --
# @File: sliding.py
# @Time: 2025/9/19 14:48
# @Author: windyzhao
from typing import List, Tuple

from apps.alerts.common.aggregation.window_processor.base import BaseWindowProcessor
from apps.alerts.models import CorrelationRules
from apps.alerts.common.aggregation.alert_processor import AlertProcessor
from apps.core.logger import alert_logger as logger


class SlidingWindowProcessor(BaseWindowProcessor):
    """滑动窗口处理器

    特点：
    - 每分钟都执行
    - 窗口持续滑动
    - 适用于实时监控场景
    """

    def get_window_type(self) -> str:
        return "sliding"

    def process_rules(self, rules: List[CorrelationRules]) -> Tuple[int, int]:
        """
        处理滑动窗口规则

        滑动窗口处理逻辑：
        1. 按窗口大小分组处理
        2. 每个窗口大小使用专门的处理器
        3. 实时性要求高，每分钟执行一次
        """
        logger.info(f"开始处理滑动窗口规则，数量: {len(rules)}")

        # 按窗口大小分组规则
        grouped_rules = self._group_rules_by_window_size(rules)

        total_format_alerts = []
        total_update_alerts = []

        # 按窗口大小分组处理
        for window_size, size_rules in grouped_rules.items():
            logger.info(f"处理窗口大小 {window_size} 的滑动窗口规则，数量: {len(size_rules)}")

            try:
                # 为每个窗口大小创建专门的处理器
                processor = AlertProcessor(window_size=window_size)

                # 批量处理该窗口大小的规则
                batch_alerts, batch_updates = processor._process_batch_correlation_rules(
                    size_rules, self.get_window_type()
                )

                total_format_alerts.extend(batch_alerts)
                total_update_alerts.extend(batch_updates)

                logger.info(
                    f"窗口大小 {window_size} 处理完成，产生 {len(batch_alerts)} 个新告警，{len(batch_updates)} 个更新")

            except Exception as e:
                logger.error(f"窗口大小 {window_size} 的滑动窗口规则处理失败: {str(e)}")
                continue

        logger.info(f"滑动窗口处理完成，总计产生 {len(total_format_alerts)} 个新告警，{len(total_update_alerts)} 个更新")

        return self._execute_processing(total_format_alerts, total_update_alerts)
