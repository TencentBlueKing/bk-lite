# -- coding: utf-8 --
# @File: auto_close.py
# @Time: 2025/7/29 17:28
# @Author: windyzhao
from datetime import timedelta
from django.db import transaction
from django.utils import timezone

from apps.alerts.constants import (
    AlertStatus,
    LogAction,
    LogTargetType,
    AlertOperate,
    SessionStatus,
)
from apps.alerts.models import Alert, AlarmStrategy, OperatorLog
from apps.alerts.utils.util import split_list
from apps.core.logger import alert_logger as logger


class WindowCalculator:
    """窗口时间计算器"""

    @staticmethod
    def parse_time_str(time_str: str) -> timedelta:
        """解析时间字符串为timedelta对象"""
        if time_str.endswith('min'):
            return timedelta(minutes=int(time_str[:-3]))
        elif time_str.endswith('h'):
            return timedelta(hours=int(time_str[:-1]))
        elif time_str.endswith('d'):
            return timedelta(days=int(time_str[:-1]))
        elif time_str.endswith('s'):
            return timedelta(seconds=int(time_str[:-1]))
        else:
            # 默认按分钟处理
            return timedelta(minutes=int(time_str))


class AlertAutoClose:
    """
    判断自动关闭告警
    关闭时间从告警的AlarmStrategy的close_minutes字段获取
    1. 获取所有没有关闭的告警
    2. 获取告警的第一个event和最后一个event的时间
    3. 判断当前时间是否超过了关闭时间
    """

    def __init__(self):
        self.alerts = self.get_alerts()
        self.rule_id_to_strategy = self.build_rule_mapping()
        self.bulk_logs = []
        self.current_time = timezone.now()

    @staticmethod
    def get_alerts():
        """
        获取所有未关闭的告警
        """
        return Alert.objects.filter(status__in=AlertStatus.ACTIVATE_STATUS)

    def build_rule_mapping(self):
        """
        建立 alert.rule_id 到 AlarmStrategy 的映射关系
        提前过滤掉不需要自动关闭的策略，减少后续处理压力
        """
        # 获取所有告警的 rule_id
        rule_ids = list(self.alerts.values_list('rule_id', flat=True).distinct())
        rule_ids = [rid for rid in rule_ids if isinstance(rid, str) and rid.isdigit()]
        # 查询启用了自动关闭的告警策略
        # 过滤条件：is_active=True, auto_close=True, close_minutes > 0
        strategies = AlarmStrategy.objects.filter(
            id__in=rule_ids,
            is_active=True,
            auto_close=True,
            close_minutes__gt=0
        )

        # 建立映射字典: rule_id -> AlarmStrategy
        rule_mapping = {str(strategy.id): strategy for strategy in strategies}

        return rule_mapping

    @staticmethod
    def get_alert_event_times(alert):
        """
        获取告警的首次和最近事件时间
        直接使用Alert模型的时间字段
        """
        return alert.first_event_time, alert.last_event_time

    def should_auto_close(self, alert: Alert, strategy: AlarmStrategy) -> bool:
        """
        判断告警是否应该自动关闭

        Args:
            alert: 告警对象
            strategy: 告警策略对象

        Returns:
            是否应该自动关闭
        """
        try:
            # 由于在 build_rule_mapping 中已经过滤了无效配置，这里可以简化检查
            # 但保留基础检查作为安全措施
            if not strategy.auto_close or strategy.close_minutes <= 0:
                logger.debug(
                    f"告警 {alert.id} 的策略 {strategy.id} 配置为不自动关闭 (auto_close={strategy.auto_close}, close_minutes={strategy.close_minutes})")
                return False

            # 会话窗口在未确认前不参与自动关闭倒计时
            if alert.is_session_alert and alert.session_status in SessionStatus.NO_CONFIRMED:
                logger.debug(
                    "告警 %s 为会话窗口且尚未确认，跳过自动关闭计算",
                    alert.alert_id,
                )
                return False

            # 获取告警的事件时间
            first_event_time, last_event_time = self.get_alert_event_times(alert)

            # 检查必要的时间字段
            if not last_event_time:
                logger.warning(f"告警 {alert.id} 缺少最后事件时间，无法判断自动关闭条件")
                return False

            # 计算自动关闭时间点（close_minutes是整数分钟数）
            auto_close_time = last_event_time + timedelta(minutes=strategy.close_minutes)

            # 判断是否到达自动关闭时间
            should_close = self.current_time >= auto_close_time

            if should_close:
                logger.info(
                    f"告警 {alert.id} 满足自动关闭条件: "
                    f"最后事件时间={last_event_time}, "
                    f"关闭时间配置={strategy.close_minutes}分钟, "
                    f"自动关闭时间点={auto_close_time}, "
                    f"当前时间={self.current_time}"
                )
            else:
                logger.debug(
                    f"告警 {alert.id} 暂不满足自动关闭条件: "
                    f"距离自动关闭还有 {(auto_close_time - self.current_time).total_seconds() / 60:.1f} 分钟"
                )

            return should_close

        except Exception as e:
            logger.error(f"判断告警 {alert.id} 是否应该自动关闭时发生错误: {str(e)}")
            return False

    def auto_close_alert(self, alert: Alert, strategy: AlarmStrategy) -> bool:
        """
        自动关闭告警

        Args:
            alert: 要关闭的告警对象
            strategy: 告警策略对象

        Returns:
            是否成功关闭
        """
        try:
            # 使用数据库事务和行锁确保并发安全
            with transaction.atomic():
                # 使用select_for_update加行锁，避免并发更新冲突
                locked_alert = Alert.objects.select_for_update().get(id=alert.id)

                # 再次检查告警状态，防止在等待锁期间被其他进程处理
                if locked_alert.status not in AlertStatus.ACTIVATE_STATUS:
                    logger.info(f"告警 {alert.id} 已被其他进程处理，当前状态: {locked_alert.status}")
                    return False

                # 更新告警状态为已关闭
                locked_alert.updated_at = timezone.now()
                locked_alert.operate = AlertOperate.CLOSE
                locked_alert.status = AlertStatus.AUTO_CLOSE
                locked_alert.save(update_fields=['status', 'updated_at', 'operate'])

                # 记录操作日志
                logs = OperatorLog(
                    action=LogAction.MODIFY,
                    target_type=LogTargetType.ALERT,
                    operator="system",
                    operator_object="告警处理-自动关闭",
                    target_id=alert.alert_id,
                    overview=f"告警自动关闭, 告警标题[{alert.title}], 触发策略[{strategy.name}], 超时关闭时间[{strategy.close_minutes}分钟]",
                )
                self.bulk_logs.append(logs)

                logger.info(f"成功自动关闭告警 {alert.id}")
                return True

        except Alert.DoesNotExist:
            logger.warning(f"告警 {alert.id} 不存在，可能已被删除")
            return False
        except Exception as e:
            logger.error(f"自动关闭告警 {alert.alert_id} 失败: {str(e)}")
            return False

    def main(self):
        """
        主逻辑：检查告警是否可以自动关闭

        处理流程：
        1. 遍历所有活跃告警
        2. 获取对应的关联规则
        3. 判断是否满足自动关闭条件
        4. 执行自动关闭操作
        """
        logger.info("开始执行告警自动关闭检查")

        if not self.alerts.exists():
            logger.info("当前没有需要检查的活跃告警")
            return

        # 检查有效的策略映射数量
        if not self.rule_id_to_strategy:
            logger.info("当前没有配置有效自动关闭时间的策略，跳过处理")
            return

        closed_count = 0
        error_count = 0
        total_alerts = self.alerts.count()

        # 只处理有对应策略的告警，进一步减少处理量
        valid_alerts = self.alerts.filter(rule_id__in=list(self.rule_id_to_strategy.keys()))
        valid_alert_count = valid_alerts.count()

        logger.info(f"开始检查 {total_alerts} 个活跃告警，其中 {valid_alert_count} 个告警有有效的自动关闭策略")

        # 分批处理，避免一次性处理太多告警导致内存或性能问题
        batch_alerts = split_list(valid_alerts, count=200)

        for alert_list in batch_alerts:
            for alert in alert_list:
                try:
                    strategy = self.rule_id_to_strategy[alert.rule_id]
                    # 判断是否应该自动关闭
                    if self.should_auto_close(alert, strategy):
                        # 执行自动关闭
                        if self.auto_close_alert(alert, strategy):
                            closed_count += 1
                        else:
                            error_count += 1

                except Exception as e:
                    logger.error(f"处理告警 {alert.id} 时发生错误: {str(e)}")
                    error_count += 1

        logger.info(
            f"告警自动关闭检查完成: "
            f"总检查数={valid_alert_count}, "
            f"成功关闭数={closed_count}, "
            f"错误数={error_count}"
        )

        OperatorLog.objects.bulk_create(self.bulk_logs, batch_size=200)
