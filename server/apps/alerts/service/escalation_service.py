# -- coding: utf-8 --
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.db import connection, transaction
from django.utils import timezone

from apps.alerts.constants.constants import AlertStatus, SessionStatus
from apps.alerts.models.alert_operator import (
    AlertAssignment,
    AlertEscalationTask,
    AlertReminderTask,
)
from apps.alerts.models.models import Alert

logger = logging.getLogger(__name__)

VALID_MODES = ("append", "replace")


class EscalationService:
    EXPIRED_DAYS = 30

    @staticmethod
    def parse_escalation_config(config: Optional[dict]) -> Optional[dict]:
        """解析并规范化升级链配置。无效或未启用返回 None。"""
        if not config:
            return None
        block = config.get("escalation") if isinstance(config, dict) else None
        if not block or not block.get("enabled"):
            return None
        mode = block.get("mode")
        if mode not in VALID_MODES:
            logger.warning("升级链模式非法: mode=%s", mode)
            return None
        raw_layers = block.get("layers") or []
        if not isinstance(raw_layers, list) or len(raw_layers) == 0:
            return None
        layers: List[dict] = []
        for idx, layer in enumerate(raw_layers):
            personnel = layer.get("personnel") or []
            if not isinstance(personnel, list) or len(personnel) == 0:
                logger.warning("升级链第 %s 层缺少处理人", idx)
                return None
            try:
                wait_minutes = int(layer.get("wait_minutes", 0) or 0)
            except (TypeError, ValueError):
                return None
            if wait_minutes <= 0:
                logger.warning("升级链第 %s 层等待时长非法: %s", idx, layer.get("wait_minutes"))
                return None
            layers.append({
                "personnel": list(dict.fromkeys(personnel)),
                "wait_minutes": wait_minutes,
                "notify_channels": layer.get("notify_channels") or [],
            })
        return {"mode": mode, "layers": layers}

    @staticmethod
    def compute_roster(layers: List[dict], current_index: int, mode: str) -> List[str]:
        """当前在岗集合（去重保序）。replace=本层；append=0..current 并集。"""
        if mode == "replace":
            source = layers[current_index].get("personnel", [])
        else:
            source = []
            for layer in layers[: current_index + 1]:
                source.extend(layer.get("personnel", []))
        return list(dict.fromkeys(source))

    @classmethod
    def _union_into_operator(cls, alert: Alert, personnel: List[str]) -> None:
        """把新层处理人并入 operator（认领资格累加，不移除）。"""
        merged = list(dict.fromkeys(list(alert.operator or []) + list(personnel)))
        if merged != (alert.operator or []):
            alert.operator = merged
            alert.save(update_fields=["operator", "updated_at"])

    @classmethod
    def create_escalation_task(
        cls, alert: Alert, assignment: AlertAssignment
    ) -> Optional[AlertEscalationTask]:
        """分派时创建升级任务（命中规则配了升级链才创建）。"""
        normalized = cls.parse_escalation_config(assignment.config)
        if not normalized:
            return None
        now = timezone.now()
        task, _ = AlertEscalationTask.objects.update_or_create(
            alert=alert,
            defaults={
                "assignment": assignment,
                "is_active": True,
                "mode": normalized["mode"],
                "layers": normalized["layers"],
                "current_layer_index": 0,
                "layer_started_at": now,
            },
        )
        cls._union_into_operator(alert, normalized["layers"][0]["personnel"])
        logger.info("创建升级任务: alert_id=%s, mode=%s, layers=%s",
                    alert.alert_id, normalized["mode"], len(normalized["layers"]))
        return task

    @classmethod
    def stop_escalation_task(cls, alert: Alert) -> bool:
        """认领/解决/关闭后停止升级。"""
        updated = AlertEscalationTask.objects.filter(
            alert=alert, is_active=True
        ).update(is_active=False, updated_at=timezone.now())
        return updated > 0

    @classmethod
    def reset_escalation_task(
        cls, alert: Alert, assignment: Optional[AlertAssignment]
    ) -> Optional[AlertEscalationTask]:
        """改派后升级计时重置到第 0 层。assignment 为空时沿用既有任务的策略。"""
        if assignment is None:
            existing = AlertEscalationTask.objects.filter(alert=alert).select_related("assignment").first()
            if not existing:
                return None
            assignment = existing.assignment
        return cls.create_escalation_task(alert, assignment)

    @classmethod
    def _reset_reminder_for_new_roster(cls, alert: Alert) -> None:
        """跨层后级内提醒计数归零、预算重置、重新激活（若存在提醒任务）。"""
        reminder = AlertReminderTask.objects.filter(alert=alert).first()
        if not reminder:
            return
        now = timezone.now()
        reminder.reminder_count = 0
        reminder.is_active = True
        reminder.last_reminder_time = None
        reminder.next_reminder_time = now + timedelta(
            minutes=reminder.current_frequency_minutes
        )
        reminder.save(update_fields=[
            "reminder_count", "is_active", "last_reminder_time",
            "next_reminder_time", "updated_at",
        ])

    @classmethod
    def _send_escalation_notification(
        cls, alert: Alert, assignment: AlertAssignment,
        roster: List[str], layer_channels: List[dict],
    ) -> bool:
        """升级通知：复用与提醒一致的发送出口 sync_notify。"""
        from apps.alerts.common.notify.base import NotifyParamsFormat

        if alert.is_session_alert and alert.session_status != SessionStatus.CONFIRMED:
            logger.info("升级跳过会话观察期告警: alert_id=%s", alert.alert_id)
            return False
        if not roster:
            return False
        channels = layer_channels or assignment.notify_channels or []
        if not channels:
            logger.warning("升级通知无可用渠道: alert_id=%s", alert.alert_id)
            return False

        param_format = NotifyParamsFormat(username_list=roster, alerts=[alert])
        title = param_format.format_title()
        content = param_format.format_content()
        channel_params = [{
            "username_list": roster,
            "channel_type": ch["channel_type"],
            "channel_id": ch["id"],
            "title": title,
            "content": content,
            "object_id": alert.alert_id,
            "notify_action_object": "alert",
        } for ch in channels]

        from apps.alerts.tasks import sync_notify

        def _enqueue():
            sync_notify.delay(channel_params)

        if transaction.get_connection().in_atomic_block:
            transaction.on_commit(_enqueue)
        else:
            _enqueue()
        return True

    @classmethod
    def _advance_layer(cls, task: AlertEscalationTask) -> bool:
        """推进到下一层并通知；返回是否真正升级了一层。"""
        alert = task.alert
        next_index = task.current_layer_index + 1
        now = timezone.now()
        task.current_layer_index = next_index
        task.layer_started_at = now
        # 升级是时间驱动：本层等待时长已过即推进，无论通知是否成功投递
        # （spec §3.2/§3.5：提醒因屏蔽/投递失败被跳过时升级时钟照常推进）。
        # 因此此处先持久化层级推进、再发通知；通知的同步构建部分仍在扫描的
        # transaction.atomic() 内，构建异常会连同推进一起回滚。
        task.save(update_fields=["current_layer_index", "layer_started_at", "updated_at"])

        roster = cls.compute_roster(task.layers, next_index, task.mode)
        cls._union_into_operator(alert, task.layers[next_index]["personnel"])
        cls._reset_reminder_for_new_roster(alert)
        cls._send_escalation_notification(
            alert, task.assignment, roster, task.layers[next_index].get("notify_channels") or []
        )
        logger.info("告警升级到第 %s 层: alert_id=%s, roster=%s",
                    next_index, alert.alert_id, roster)
        return True

    @classmethod
    def check_and_process_escalations(cls) -> Dict[str, Any]:
        """每分钟扫描：到本层等待时长且仍待响应则升级到下一层。"""
        processed = 0
        escalated = 0
        try:
            ids = list(
                AlertEscalationTask.objects.filter(is_active=True).values_list(
                    "alert_id", flat=True
                )
            )
            select_for_update_kwargs = {}
            if connection.features.has_select_for_update_skip_locked:
                select_for_update_kwargs["skip_locked"] = True

            for alert_id in ids:
                try:
                    with transaction.atomic():
                        task = (
                            AlertEscalationTask.objects.select_for_update(
                                **select_for_update_kwargs
                            )
                            .select_related("alert", "assignment")
                            .filter(alert_id=alert_id, is_active=True)
                            .first()
                        )
                        if not task:
                            continue
                        processed += 1

                        if task.alert.status != AlertStatus.PENDING:
                            task.is_active = False
                            task.save(update_fields=["is_active", "updated_at"])
                            continue

                        deadline = task.layer_started_at + timedelta(
                            minutes=task.layers[task.current_layer_index]["wait_minutes"]
                        )
                        if timezone.now() < deadline:
                            continue

                        is_last = task.current_layer_index >= len(task.layers) - 1
                        if is_last:
                            task.is_active = False
                            task.save(update_fields=["is_active", "updated_at"])
                            logger.info("告警已达最后一层，不再升级: alert_id=%s", task.alert.alert_id)
                            continue

                        if cls._advance_layer(task):
                            escalated += 1
                except Exception as e:
                    logger.error("处理升级任务失败: alert_id=%s, error=%s", alert_id, str(e))
        except Exception as e:
            logger.error("检查升级任务失败: %s", str(e))
        return {"processed": processed, "escalated": escalated}

    @classmethod
    def cleanup_expired_escalations(cls) -> int:
        cutoff = timezone.now() - timedelta(days=cls.EXPIRED_DAYS)
        deleted, _ = AlertEscalationTask.objects.filter(
            is_active=False, updated_at__lt=cutoff
        ).delete()
        return deleted
