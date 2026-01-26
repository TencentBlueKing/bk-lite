from datetime import timedelta
from typing import List, Dict, Any
import logging

from django.utils import timezone
from django.db import transaction

from apps.alerts.aggregation.recovery.recovery_checker import AlertRecoveryChecker
from apps.alerts.models import AlarmStrategy, Event
from apps.alerts.constants import EventAction, AlarmStrategyType
from apps.alerts.aggregation.strategy.matcher import StrategyMatcher
from apps.alerts.aggregation.window.factory import WindowFactory
from apps.alerts.aggregation.query.builder import SQLBuilder
from apps.alerts.aggregation.engine.connection import DuckDBConnection
from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.core.logger import alert_logger as logger


class AggregationProcessor:
    """
    聚合处理器 - 基于AlarmStrategy处理事件聚合

    使用AlarmStrategy模型（strategy_type=smart_denoise）
    """

    def __init__(self):
        self.sql_builder = SQLBuilder()
        self.db_conn = DuckDBConnection()

    def process_aggregation(self):
        """执行聚合处理"""
        try:
            active_strategies = self._get_active_strategies()
            if not active_strategies:
                logger.info("无活跃告警策略，跳过聚合处理")
                return

            logger.info(f"开始处理 {len(active_strategies)} 个活跃策略")

            for strategy in active_strategies:
                logger.info(f"处理策略: {strategy.name} (ID: {strategy.id})")
                self._process_strategy(strategy)

            logger.info("所有策略处理完成")

        except Exception as e:
            logger.exception(f"聚合处理失败: {e}")
            raise
        finally:
            self.db_conn.close()

    def _get_active_strategies(self) -> List[AlarmStrategy]:
        """获取所有活跃的智能降噪策略
        {
            "name": "测试规则", //策略名称
            "strategy_type": "smart_denoise", //智能降噪  missing_detection 缺失检测
            "description": "描述",
            "team": [
                1
            ], //组织
            "dispatch_team": [
                1
            ], //分派组织
            "match_rules": [
                [
                    {
                        "key": "title",
                        "value": "1",
                        "operator": "eq"
                    },
                    {
                        "key": "content",
                        "operator": "re",
                        "value": "2"
                    }
                ],
                [
                    {
                        "key": "level_id",
                        "value": 2,
                        "operator": "eq"
                    }
                ]
            ], //匹配规则
            "params": {
                "group_by": [
                    "service"
                ], //策略，service应用，location基础设施,resource_name实例,[""]其他
                "window_size": 10, //窗口
                "time_out": true, //自愈检查
                "time_minutes": 10 //观察时间
            },
            "auto_close": true, //是否自动关闭告警
            "close_minutes": 120 //自动关闭时间
        }
        """
        # 要求 每个策略查询的事件是不一样的，包括时间窗口和过滤条件
        return list(
            AlarmStrategy.objects.filter(
                is_active=True,
                strategy_type=AlarmStrategyType.SMART_DENOISE,
            ).order_by("-updated_at")
        )

    @staticmethod
    def get_events_for_strategy(strategy: AlarmStrategy):
        """
        根据策略配置获取事件
        每个策略有自己的时间窗口和过滤条件
        """
        params = strategy.params or {}
        window_size = params.get("window_size", 10)

        cutoff_time = timezone.now() - timedelta(minutes=window_size)

        logger.info(
            f"策略 {strategy.name}: 查询时间窗口={window_size}分钟, "
            f"起始时间={cutoff_time.isoformat()}"
        )

        events = Event.objects.filter(
            received_at__gte=cutoff_time, action=EventAction.CREATED
        )

        logger.debug(f"策略 {strategy.name}: 时间范围内事件总数={events.count()}")

        return events

    def _process_strategy(self, strategy: AlarmStrategy):
        """
        处理单个告警策略

        每个策略独立处理：
        1. 根据策略的window_size获取对应时间范围的事件
        2. 根据策略的match_rules过滤匹配的事件
        3. 根据策略的params.group_by字段进行聚合
        """
        try:
            events = self.get_events_for_strategy(strategy)

            if not events.exists():
                logger.info(f"策略 {strategy.name}: 无事件需要处理")
                return

            matched_events = StrategyMatcher.match_events_to_strategy(events, strategy.match_rules)

            if not matched_events.exists():
                logger.info(f"策略 {strategy.name}: 无匹配规则的事件")
                return

            params = strategy.params or {}
            dimensions = params.get("group_by", []) or ["event_id"]
            logger.info(f"策略 {strategy.name}: 聚合维度={dimensions}")

            if self._aggregate_for_dimensions(strategy, matched_events, dimensions):
                logger.info(f"策略 {strategy.name}: 维度 {dimensions} 聚合成功")

        except Exception as e:  # noqa
            import traceback
            logger.error(f"策略 {strategy.name} 处理失败: {traceback.format_exc()}")

    def _aggregate_for_dimensions(
            self, strategy: AlarmStrategy, events, dimensions: List[str]
    ) -> bool:
        """对指定维度执行聚合"""
        try:

            # 优化：直接使用已过滤的 events QuerySet，避免重复查询
            load_success = self.db_conn.load_events_to_memory(events)
            if not load_success:
                logger.info(f"策略 {strategy.name}过滤后无事件，跳过聚合")
                return False

            window_config = WindowFactory.create_from_strategy(strategy)

            logger.debug(
                f"策略 {strategy.name}: 窗口配置 "
                f"type={window_config.window_type}, "
                f"size={window_config.window_size_minutes}分钟"
            )

            sql_query = self.sql_builder.build_aggregation_sql(
                dimensions=dimensions,
                window_config=window_config,
                strategy_id=strategy.id,
            )

            logger.debug(f"策略 {strategy.name}: 执行聚合SQL")

            results = self.db_conn.execute_query(sql_query)

            if not results:
                logger.info(f"策略 {strategy.name}: 聚合结果为空")
                return False

            logger.info(f"策略 {strategy.name}: 聚合完成, 生成 {len(results)} 个告警组")

            self._create_or_update_alerts(results, strategy, dimensions)
            return True

        except Exception as e:
            logger.error(
                f"策略 {strategy.name}: 维度 {dimensions} 聚合失败: {e}", exc_info=True
            )
            return False

    def _create_or_update_alerts(
            self,
            aggregation_results: List[Dict[str, Any]],
            strategy: AlarmStrategy,
            dimensions: List[str],
    ):
        """创建或更新告警"""

        logger.info(
            f"策略 {strategy.name}: 开始创建/更新告警, "
            f"结果数={len(aggregation_results)}"
        )

        success_count = 0
        fail_count = 0
        recovered_count = 0

        for result in aggregation_results:
            try:
                with transaction.atomic():
                    alert = AlertBuilder.create_or_update_alert(
                        aggregation_result=result,
                        strategy=strategy,
                        group_by_field=",".join(dimensions),
                    )

                    # 检查是否应该自动恢复
                    if AlertRecoveryChecker.check_and_recover_alert(alert):
                        recovered_count += 1

                    success_count += 1
                    logger.debug(
                        f"策略 {strategy.name}: 告警处理成功 "
                        f"fingerprint={result.get('fingerprint')}"
                    )
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"策略 {strategy.name}: 告警创建/更新失败 "
                    f"fingerprint={result.get('fingerprint')}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"策略 {strategy.name}: 告警处理完成, "
            f"成功={success_count}, 失败={fail_count}, 自动恢复={recovered_count}"
        )
