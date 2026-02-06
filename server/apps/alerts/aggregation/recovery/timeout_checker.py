from django.utils import timezone
from apps.alerts.models.models import Alert
from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.core.logger import alert_logger as logger


class TimeoutChecker:
    """会话窗口超时检查器"""

    @staticmethod
    def check_session_timeouts():
        """
        检查并处理超时的会话窗口告警

        逻辑：
        1. 查询所有 is_session_alert=True 且 session_status=observing 的告警
        2. 检查 session_end_time 是否已过期
        3. 过期的告警：session_status 从 observing 改为 confirmed
        """
        now = timezone.now()

        # 查询观察中的会话窗口告警
        observing_alerts = Alert.objects.filter(
            is_session_alert=True,
            session_status=SessionStatus.OBSERVING,
            status__in=AlertStatus.ACTIVATE_STATUS,
            session_end_time__isnull=False,
        )

        logger.info(f"开始检查会话超时，观察中的告警数={observing_alerts.count()}")

        confirmed_count = 0
        for alert in observing_alerts:
            if alert.session_end_time <= now:
                TimeoutChecker._confirm_session_alert(alert)
                confirmed_count += 1

        logger.info(f"会话超时检查完成，确认告警数={confirmed_count}")
        return confirmed_count

    @staticmethod
    def _confirm_session_alert(alert: Alert):
        """
        确认会话窗口告警（超时未恢复）

        session_status: observing -> confirmed
        保持 Alert 处于活跃状态（不自动关闭）
        """
        alert.session_status = SessionStatus.CONFIRMED
        alert.save(update_fields=["session_status", "updated_at"])

        logger.info(
            f"会话窗口超时确认: alert_id={alert.alert_id}, "
            f"fingerprint={alert.fingerprint}, "
            f"session_end_time={alert.session_end_time.isoformat()}"
        )

    @staticmethod
    def confirm_observing_alerts_by_strategy(strategy_id: int):
        """
        确认指定策略关联的所有观察中告警

        用于策略会话配置变更时，立即确认观察中的告警

        Args:
            strategy_id: 告警策略ID

        Returns:
            int: 确认的告警数量
        """
        observing_alerts = Alert.objects.filter(
            rule_id=strategy_id,
            is_session_alert=True,
            session_status=SessionStatus.OBSERVING,
            status__in=AlertStatus.ACTIVATE_STATUS,
        )

        confirmed_count = 0
        for alert in observing_alerts:
            alert.session_status = SessionStatus.CONFIRMED
            alert.save(update_fields=["session_status", "updated_at"])
            confirmed_count += 1

            logger.info(
                f"策略变更确认告警: strategy_id={strategy_id}, "
                f"alert_id={alert.alert_id}, fingerprint={alert.fingerprint}"
            )

        logger.info(
            f"策略变更确认完成: strategy_id={strategy_id}, 确认告警数={confirmed_count}"
        )

        return confirmed_count

    @staticmethod
    def close_observing_session_alerts_by_strategy(strategy_id: int):
        """
        关闭指定会话策略关联的观察中告警

        用于会话策略删除时，关闭观察中的会话告警

        Args:
            strategy_id: 告警策略ID

        Returns:
            int: 关闭的告警数量
        """
        observing_alerts = Alert.objects.filter(
            rule_id=strategy_id,
            is_session_alert=True,
            session_status=SessionStatus.OBSERVING,
            status__in=AlertStatus.ACTIVATE_STATUS,
        )

        closed_count = 0
        for alert in observing_alerts:
            original_status = alert.status
            alert.status = AlertStatus.CLOSED
            alert.session_status = SessionStatus.RECOVERED
            alert.save(update_fields=["status", "updated_at","session_status"])
            closed_count += 1

            logger.info(
                f"会话策略删除关闭告警: strategy_id={strategy_id}, "
                f"alert_id={alert.alert_id}, fingerprint={alert.fingerprint}, "
                f"原状态={original_status}, session_status=OBSERVING"
            )

        logger.info(
            f"会话策略删除关闭完成: strategy_id={strategy_id}, "
            f"关闭观察中告警数={closed_count}"
        )

        return closed_count
