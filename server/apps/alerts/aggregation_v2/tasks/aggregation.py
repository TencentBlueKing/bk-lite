# -- coding: utf-8 --
"""
V2 聚合任务

提供新版本的事件聚合调度任务
"""
from django.utils import timezone

from apps.alerts.models import CorrelationRules
from apps.alerts.aggregation_v2.processors.factory import WindowProcessorFactory
from apps.alerts.aggregation_v2.rules.adapter import RuleAdapter
from apps.alerts.aggregation_v2.query.optimizer import QueryOptimizer
from apps.alerts.aggregation_v2.utils.metrics import PerformanceMonitor
from apps.core.logger import alert_logger as logger


def process_event_aggregation_v2(rule_id: int):
    """
    处理单个规则的事件聚合（V2版本）
    
    Args:
        rule_id: 关联规则 ID

    Returns:
        聚合结果统计
    """
    try:
        with PerformanceMonitor(f"规则聚合-{rule_id}", rule_id=rule_id) as pm:
            # 1. 获取规则
            correlation_rule = CorrelationRules.objects.filter(id=rule_id).first()

            if correlation_rule is None:
                logger.info(f"规则 {rule_id} 未启用，跳过处理")
                return {"status": "skipped", "reason": "inactive"}

            # 2. 智能调度检查（是否有新事件）
            if QueryOptimizer.should_skip_query(rule_id):
                logger.info(f"规则 {rule_id} 无新事件，跳过处理")
                return {"status": "skipped", "reason": "no_new_events"}

            # 3. 创建窗口处理器
            processor = WindowProcessorFactory.create(correlation_rule)

            # 4. 执行聚合
            alerts = processor.process()

            # 5. 更新查询时间
            QueryOptimizer.update_last_query_time(rule_id)

            # 6. 统计结果
            alert_count = len(alerts) if isinstance(alerts, list) else 0
            stats = {
                "status": "success",
                "rule_id": rule_id,
                "rule_name": correlation_rule.name,
                "window_type": correlation_rule.window_type,
                "strategy_type": correlation_rule.strategy_type,
                "alert_count": alert_count,
                "duration_ms": pm.elapsed_ms,
                "timestamp": timezone.now().isoformat()
            }

            logger.info(
                f"规则 {rule_id} 聚合完成: 生成 {alert_count} 个告警, "
                f"耗时 {pm.elapsed_ms:.2f}ms"
            )

            return stats

    except CorrelationRules.DoesNotExist:
        logger.error(f"规则 {rule_id} 不存在")
        return {"status": "error", "reason": "rule_not_found"}
    except Exception as e:
        import traceback
        logger.error(f"规则 {rule_id} 聚合失败: {traceback.format_exc()}", exc_info=True)
        return {"status": "error", "reason": str(e)}


def schedule_all_rules():
    """
    调度所有活跃规则的聚合任务
    self 参数用于绑定任务实例（可选）
    Returns:
        调度统计
    """
    try:
        with PerformanceMonitor("全规则调度") as pm:
            # 1. 获取所有活跃规则
            active_rules = RuleAdapter.get_active_rules()

            if not active_rules:
                logger.info("没有活跃规则，跳过调度")
                return {
                    "status": "success",
                    "scheduled_count": 0,
                    "message": "no_active_rules"
                }

            # 2. 按优先级排序
            sorted_rules = RuleAdapter.sort_rules_by_priority(active_rules)

            # 3. 调度每个规则
            scheduled_count = 0
            for rule in sorted_rules:
                try:
                    # 异步调度
                    process_event_aggregation_v2(rule.id)
                    scheduled_count += 1
                except Exception as e:
                    logger.error(f"调度规则 {rule.id} 失败: {e}")

            logger.info(
                f"规则调度完成: 成功={scheduled_count}/{len(sorted_rules)}, "
                f"耗时={pm.elapsed_ms:.2f}ms"
            )

            return {
                "status": "success",
                "total_rules": len(active_rules),
                "scheduled_count": scheduled_count,
                "duration_ms": pm.elapsed_ms,
                "timestamp": timezone.now().isoformat()
            }

    except Exception as e:
        logger.error(f"规则调度失败: {e}", exc_info=True)
        return {"status": "error", "reason": str(e)}


def process_rules_by_window_type(window_type: str):
    """
    按窗口类型处理规则（可选任务，用于分批处理）
    
    Args:
        window_type: 窗口类型（fixed/sliding/session）
        
    Returns:
        处理统计
    """
    try:
        # 获取指定类型的规则
        rules = RuleAdapter.get_active_rules(window_type=window_type)

        if not rules:
            logger.info(f"没有 {window_type} 类型的活跃规则")
            return {
                "status": "success",
                "window_type": window_type,
                "processed_count": 0
            }

        # 调度处理
        for rule in rules:
            process_event_aggregation_v2(rule.id)

        logger.info(f"调度 {window_type} 规则: {len(rules)} 个")

        return {
            "status": "success",
            "window_type": window_type,
            "processed_count": len(rules)
        }

    except Exception as e:
        logger.error(f"按窗口类型处理失败: {e}", exc_info=True)
        return {"status": "error", "reason": str(e)}
