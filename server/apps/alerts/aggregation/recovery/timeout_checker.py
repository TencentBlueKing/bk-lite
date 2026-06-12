from django.db import transaction
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

        logger.info("[AlertRecovery] 开始检查会话超时，观察中的告警数=%s", observing_alerts.count())

        confirmed_count = 0
        for alert in observing_alerts:
            if alert.session_end_time <= now:
                TimeoutChecker._confirm_session_alert(alert)
                confirmed_count += 1

        logger.info("[AlertRecovery] 会话超时检查完成，确认告警数=%s", confirmed_count)
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
        TimeoutChecker._trigger_auto_assignment(alert)

        logger.info(
            "[AlertRecovery] 会话窗口超时确认: alert_id=%s, fingerprint=%s, session_end_time=%s",
            alert.alert_id, alert.fingerprint, alert.session_end_time.isoformat(),
        )

    @staticmethod
    def _trigger_auto_assignment(alert: Alert):
        """会话转正后触发一次自动分派"""
        from apps.alerts.tasks import async_auto_assignment_for_alerts

        try:
            async_auto_assignment_for_alerts.delay([alert.alert_id])
            logger.info(
                "[AlertRecovery] 会话窗口告警触发自动分派: alert_id=%s, session_status=%s",
                alert.alert_id,
                alert.session_status,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "[AlertRecovery] 会话窗口告警触发自动分派失败 alert_id=%s, error=%s",
                alert.alert_id,
                exc,
            )

    @staticmethod
    def _trigger_auto_assignment_for_alert_ids(alert_ids):
        """在事务提交后批量触发自动分派"""
        if not alert_ids:
            return

        from apps.alerts.tasks import async_auto_assignment_for_alerts

        unique_alert_ids = list(dict.fromkeys(alert_ids))

        def _dispatch():
            try:
                async_auto_assignment_for_alerts.delay(unique_alert_ids)
                logger.info(
                    "[AlertRecovery] 策略变更确认后触发自动分派: alert_ids=%s",
                    unique_alert_ids,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "[AlertRecovery] 策略变更确认后触发自动分派失败 alert_ids=%s, error=%s",
                    unique_alert_ids,
                    exc,
                )

        transaction.on_commit(_dispatch)

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
        confirmed_alert_ids = []
        for alert in observing_alerts:
            alert.session_status = SessionStatus.CONFIRMED
            alert.save(update_fields=["session_status", "updated_at"])
            confirmed_count += 1
            confirmed_alert_ids.append(alert.alert_id)

            logger.info(
                "[AlertRecovery] 策略变更确认告警: strategy_id=%s, alert_id=%s, fingerprint=%s",
                strategy_id, alert.alert_id, alert.fingerprint,
            )

        TimeoutChecker._trigger_auto_assignment_for_alert_ids(confirmed_alert_ids)

        logger.info(
            "[AlertRecovery] 策略变更确认完成: strategy_id=%s, 确认告警数=%s",
            strategy_id, confirmed_count,
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
                "[AlertRecovery] 会话策略删除关闭告警: strategy_id=%s, alert_id=%s, fingerprint=%s, 原状态=%s, session_status=OBSERVING",
                strategy_id, alert.alert_id, alert.fingerprint, original_status,
            )

        logger.info(
            "[AlertRecovery] 会话策略删除关闭完成: strategy_id=%s, 关闭观察中告警数=%s",
            strategy_id, closed_count,
        )

        return closed_count
