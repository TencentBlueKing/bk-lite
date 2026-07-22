import hashlib
import json
import re
from ast import literal_eval
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.cmdb.constants.subscription import NOTIFICATION_MAX_DISPLAY_INSTANCES, TRIGGER_TYPE_CHOICES, TriggerType
from apps.cmdb.models.subscription_delivery import SubscriptionDelivery, SubscriptionDeliveryStatus
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.subscription_trigger import SubscriptionTriggerService, TriggerEvent
from apps.cmdb.utils.subscription_utils import get_inst_display_name
from apps.core.logger import cmdb_logger as logger
from apps.rpc.system_mgmt import SystemMgmt


class SubscriptionTaskService:
    """
    订阅通知任务服务。

    职责：
    - 定时检查订阅规则并触发事件检测（check_rules）
    - 发送订阅通知到指定渠道（send_notifications）
    - 构建通知内容（标题、正文、接收人）

    调度机制：
    - check_rules 由 Celery Beat 定时调度，检测完成后异步派发 delivery ID
    - send_notifications 使用数据库条件抢占保证同一投递不会被并发重复处理
    - 超过租约时间的 SENDING 记录恢复为 RETRY，避免 Worker 崩溃造成永久卡死
    """

    SEND_TASK_NAME = "apps.cmdb.tasks.celery_tasks.send_subscription_notifications"
    MAX_SEND_ATTEMPTS = 3
    RETRY_BACKOFF_SECONDS = (60, 300, 900)
    SENDING_LEASE_TIMEOUT_SECONDS = 900

    @classmethod
    def check_rules(cls) -> None:
        # 定时入口：逐条规则执行触发检测，并将事件直接派发给异步发送任务。
        logger.info("[Subscription] 开始检查订阅规则")
        rule_ids = list(SubscriptionRule.objects.filter(is_enabled=True).values_list("id", flat=True))
        count = len(rule_ids)
        queued_delivery_ids = cls._get_ready_delivery_ids()
        logger.info(f"[Subscription] 共 {count} 条启用规则")
        if not count:
            if queued_delivery_ids:
                cls._dispatch_send_notifications_async(
                    source="recovery_scan", delivery_ids=queued_delivery_ids,
                )
            else:
                logger.info("[Subscription] 没有启用的订阅规则和待投递记录，跳过检查")
            return
        for rule_id in rule_ids:
            try:
                with transaction.atomic():
                    rule = SubscriptionRule.objects.select_for_update().get(id=rule_id, is_enabled=True,)
                    logger.info(f"[Subscription] 处理规则 rule_id={rule.id}, name={rule.name}")
                    service = SubscriptionTriggerService(rule)
                    events = service.process()
                    logger.info("[Subscription] 规则检测完成 " f"rule_id={rule.id}, events_count={len(events)}")
                    if not events:
                        continue

                    event_groups = cls._build_event_groups(events)
                    queued_delivery_ids.extend(cls._persist_event_groups(rule, event_groups))
                    for event in events:
                        logger.info(f"[Subscription] 检测到触发事件 rule_id={rule.id}, trigger_type={event.trigger_type}")
            except Exception as exc:
                logger.error(
                    f"[Subscription] 处理规则失败 rule_id={rule_id}, error={exc}", exc_info=True,
                )
        if queued_delivery_ids:
            queued_delivery_ids = list(dict.fromkeys(queued_delivery_ids))
            cls._dispatch_send_notifications_async(source="check_rules", delivery_ids=queued_delivery_ids)
        else:
            logger.info("[Subscription] 本轮无触发事件，跳过异步发送派发")
        logger.info("[Subscription] 订阅规则检查完成")

    @classmethod
    def send_notifications(cls, delivery_ids: list[int] | None = None) -> None:
        now = timezone.now()
        if delivery_ids is None:
            delivery_ids = cls._get_ready_delivery_ids(now=now)
        if not delivery_ids:
            logger.info("[Subscription] 没有可处理的投递记录")
            return

        system_mgmt_client = SystemMgmt()
        for delivery_id in delivery_ids:
            cls._process_delivery(delivery_id, system_mgmt_client)

    @classmethod
    def _process_delivery(cls, delivery_id: int, system_mgmt_client: SystemMgmt,) -> None:
        now = timezone.now()
        claimed = (
            SubscriptionDelivery.objects.filter(id=delivery_id, status__in=[SubscriptionDeliveryStatus.PENDING, SubscriptionDeliveryStatus.RETRY,],)
            .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
            .update(status=SubscriptionDeliveryStatus.SENDING, attempt_count=F("attempt_count") + 1, last_error="", updated_at=now,)
        )
        if not claimed:
            return

        delivery = SubscriptionDelivery.objects.get(id=delivery_id)
        try:
            cls._send_delivery(delivery, system_mgmt_client)
        except Exception as exc:
            status = (
                SubscriptionDeliveryStatus.FAILED
                if isinstance(exc, ValueError) or delivery.attempt_count >= cls.MAX_SEND_ATTEMPTS
                else SubscriptionDeliveryStatus.RETRY
            )
            next_retry_at = None
            if status == SubscriptionDeliveryStatus.RETRY:
                delay = cls.RETRY_BACKOFF_SECONDS[delivery.attempt_count - 1]
                next_retry_at = timezone.now() + timedelta(seconds=delay)
            SubscriptionDelivery.objects.filter(
                id=delivery_id, status=SubscriptionDeliveryStatus.SENDING, attempt_count=delivery.attempt_count,
            ).update(
                status=status, next_retry_at=next_retry_at, last_error=str(exc), updated_at=timezone.now(),
            )
            logger.error("[Subscription] 投递失败 " f"delivery_id={delivery_id}, status={status}, error={exc}")
            return

        SubscriptionDelivery.objects.filter(id=delivery_id, status=SubscriptionDeliveryStatus.SENDING, attempt_count=delivery.attempt_count,).update(
            status=SubscriptionDeliveryStatus.SENT, next_retry_at=None, sent_at=timezone.now(), updated_at=timezone.now(),
        )

    @classmethod
    def _send_delivery(cls, delivery: SubscriptionDelivery, system_mgmt_client: SystemMgmt,) -> None:
        events = cls._decode_event_dicts(delivery.events)
        if not events:
            raise ValueError("投递事件无法解码")
        rule = SubscriptionRule.objects.filter(id=delivery.rule_id_snapshot, is_enabled=True,).first()
        if rule is None:
            raise ValueError("订阅规则不存在或已停用")

        title, content = cls._build_notification_content(rule, events)
        receivers = cls._get_receivers_from_recipients(system_mgmt_client, delivery.recipients,)
        result = system_mgmt_client.send_msg_with_channel(channel_id=delivery.channel_id, title=title, content=content, receivers=receivers,)
        if not isinstance(result, dict) or not result.get("result"):
            error = result.get("message", "通知渠道返回失败") if isinstance(result, dict) else "通知渠道返回结果无效"
            raise RuntimeError(error)

    @classmethod
    def _dispatch_send_notifications_async(cls, source: str, delivery_ids: list[int]) -> None:
        try:
            from apps.core.celery import app

            app.send_task(
                cls.SEND_TASK_NAME, kwargs={"delivery_ids": delivery_ids},
            )
            logger.info("[Subscription] 异步派发通知发送成功 " f"source={source}, task={cls.SEND_TASK_NAME}, delivery_count={len(delivery_ids)}")
        except Exception as exc:
            logger.error(
                f"[Subscription] 异步派发通知发送失败 source={source}, error={exc}", exc_info=True,
            )

    @classmethod
    def _persist_event_groups(cls, rule: SubscriptionRule, event_groups: list[dict[str, Any]],) -> list[int]:
        delivery_ids: list[int] = []
        for group in event_groups:
            events = sorted(group.get("events", []), key=cls._canonical_json,)
            for channel_id in rule.channel_ids:
                dedupe_payload = {
                    "rule_id": rule.id,
                    "trigger_type": group.get("trigger_type"),
                    "channel_id": channel_id,
                    "events": events,
                }
                dedupe_key = hashlib.sha256(cls._canonical_json(dedupe_payload).encode("utf-8")).hexdigest()
                delivery, _ = SubscriptionDelivery.objects.get_or_create(
                    dedupe_key=dedupe_key,
                    defaults={
                        "rule": rule,
                        "rule_id_snapshot": rule.id,
                        "trigger_type": group.get("trigger_type", ""),
                        "events": events,
                        "recipients": rule.recipients,
                        "channel_id": channel_id,
                    },
                )
                if delivery.status == SubscriptionDeliveryStatus.PENDING or (
                    delivery.status == SubscriptionDeliveryStatus.RETRY
                    and (delivery.next_retry_at is None or delivery.next_retry_at <= timezone.now())
                ):
                    delivery_ids.append(delivery.id)
        return delivery_ids

    @classmethod
    def _get_ready_delivery_ids(cls, now=None) -> list[int]:
        now = now or timezone.now()
        SubscriptionDelivery.objects.filter(
            status=SubscriptionDeliveryStatus.SENDING, updated_at__lte=now - timedelta(seconds=cls.SENDING_LEASE_TIMEOUT_SECONDS),
        ).update(
            status=SubscriptionDeliveryStatus.RETRY, next_retry_at=now, last_error="发送租约过期，等待重试", updated_at=now,
        )
        return list(
            SubscriptionDelivery.objects.filter(
                Q(status=SubscriptionDeliveryStatus.PENDING) | Q(status=SubscriptionDeliveryStatus.RETRY, next_retry_at__lte=now,)
            ).values_list("id", flat=True)
        )

    @staticmethod
    def _canonical_json(value: Any) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,)

    @staticmethod
    def _build_event_groups(events: list[TriggerEvent]) -> list[dict[str, Any]]:
        grouped_events: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for event in events:
            group_key = (event.rule_id, event.trigger_type)
            grouped_events.setdefault(group_key, []).append(event.to_dict())

        event_groups = [
            {"rule_id": rule_id, "trigger_type": trigger_type, "events": group_events,}
            for (rule_id, trigger_type), group_events in grouped_events.items()
        ]
        logger.info(
            "[Subscription] 事件分组完成 "
            f"group_count={len(event_groups)}, "
            f"groups={[(group['rule_id'], group['trigger_type'], len(group['events'])) for group in event_groups]}"
        )
        return event_groups

    @staticmethod
    def _decode_event_dicts(items: list[dict[str, Any]]) -> list[TriggerEvent]:
        """将事件字典列表解码为 TriggerEvent 对象列表。"""
        events: list[TriggerEvent] = []
        for item in items:
            try:
                events.append(TriggerEvent(**item))
            except Exception as exc:
                logger.warning(f"[Subscription] 事件解码失败，已跳过 item={item}, error={exc}")
                continue
        return events

    @staticmethod
    def _build_notification_content(rule: SubscriptionRule, events: list[TriggerEvent]) -> tuple[str, str]:
        if not events:
            return "[CMDB 数据订阅] 规则触发", "无触发事件"

        model_name = events[0].model_name
        trigger_type = events[0].trigger_type
        event_count = len(events)

        title = SubscriptionTaskService._build_title(model_name, events, trigger_type)

        content_lines: list[str] = []
        content_lines.append(f"模型：{model_name}")

        if event_count == 1:
            event = events[0]
            content_lines.append(f"实例：{event.inst_name}")
            content_lines.append(f"触发类型：{SubscriptionTaskService._get_trigger_type_display(trigger_type)}")

            if trigger_type == TriggerType.EXPIRATION.value:
                content_lines.append(f"到期信息：{SubscriptionTaskService._format_change_summary(event)}")
            else:
                content_lines.append(f"变化摘要：{SubscriptionTaskService._format_change_summary(event)}")

            content_lines.append(f"触发时间：{SubscriptionTaskService._format_triggered_at(event.triggered_at)}")
        else:
            content_lines.append(f"触发类型：{SubscriptionTaskService._get_trigger_type_display(trigger_type)}")

            if event_count > NOTIFICATION_MAX_DISPLAY_INSTANCES:
                agg_summary = SubscriptionTaskService._build_aggregated_summary(events)
                content_lines.append(f"变化摘要：{agg_summary}")
            else:
                content_lines.append("变化摘要：")
                for i, event in enumerate(events, 1):
                    summary = SubscriptionTaskService._format_change_summary(event)
                    content_lines.append(f"{i}）{event.inst_name}：{summary}")

            times = sorted([e.triggered_at for e in events])
            min_time = SubscriptionTaskService._format_triggered_at(times[0])
            max_time = SubscriptionTaskService._format_triggered_at(times[-1])
            if min_time == max_time:
                content_lines.append(f"触发时间：{min_time}")
            else:
                content_lines.append(f"触发时间范围：{min_time} 至 {max_time}")

        content = "\n".join(content_lines)
        logger.debug(f"[Subscription] 构建通知内容 title={title}, events_count={event_count}")
        return title, content

    @staticmethod
    def _build_title(model_name: str, events: list[TriggerEvent], trigger_type: str) -> str:
        event_count = len(events)

        type_display_map = {
            TriggerType.ATTRIBUTE_CHANGE.value: ("属性变化", "个实例属性变化"),
            TriggerType.RELATION_CHANGE.value: ("关联对象变化", "个实例关联对象变化"),
            TriggerType.EXPIRATION.value: ("临近到期提醒", "个实例临近到期提醒"),
            TriggerType.INSTANCE_ADDED.value: ("出现新增实例", "个新增实例"),
            TriggerType.INSTANCE_DELETED.value: ("已删除", "个实例已删除"),
            TriggerType.CONFIG_FILE.value: ("配置文件关联", "个实例配置文件关联"),
        }

        single_suffix, multi_suffix = type_display_map.get(trigger_type, ("变化", "个实例变化"))

        if event_count == 1:
            inst_name = events[0].inst_name
            if trigger_type == TriggerType.INSTANCE_ADDED.value:
                return f"{model_name} {single_suffix}"
            return f"{model_name} {inst_name} {single_suffix}"
        else:
            return f"{model_name} {event_count} {multi_suffix}"

    @staticmethod
    def _build_aggregated_summary(events: list[TriggerEvent]) -> str:
        import re

        count_by_type: dict[str, int] = {}
        modified_fields: set[str] = set()

        for event in events:
            trigger_type = event.trigger_type
            count_by_type[trigger_type] = count_by_type.get(trigger_type, 0) + 1

            if trigger_type == TriggerType.ATTRIBUTE_CHANGE.value:
                summary = event.change_summary
                field_matches = re.findall(r"([\u4e00-\u9fff\w]+)\s*:\s*", summary)
                modified_fields.update(field_matches)

        summary_parts: list[str] = []
        if count_by_type.get(TriggerType.INSTANCE_ADDED.value, 0) > 0:
            summary_parts.append(f"新增 {count_by_type[TriggerType.INSTANCE_ADDED.value]} 个")
        if count_by_type.get(TriggerType.ATTRIBUTE_CHANGE.value, 0) > 0:
            attr_count = count_by_type[TriggerType.ATTRIBUTE_CHANGE.value]
            if modified_fields:
                fields_str = ", ".join(sorted(modified_fields))
                summary_parts.append(f"修改 {attr_count} 个（{fields_str}）")
            else:
                summary_parts.append(f"修改 {attr_count} 个")
        if count_by_type.get(TriggerType.RELATION_CHANGE.value, 0) > 0:
            summary_parts.append(f"关联变化 {count_by_type[TriggerType.RELATION_CHANGE.value]} 个")
        if count_by_type.get(TriggerType.EXPIRATION.value, 0) > 0:
            summary_parts.append(f"到期提醒 {count_by_type[TriggerType.EXPIRATION.value]} 个")
        if count_by_type.get(TriggerType.INSTANCE_DELETED.value, 0) > 0:
            summary_parts.append(f"删除 {count_by_type[TriggerType.INSTANCE_DELETED.value]} 个")
        if count_by_type.get(TriggerType.CONFIG_FILE.value, 0) > 0:
            summary_parts.append(f"配置文件关联 {count_by_type[TriggerType.CONFIG_FILE.value]} 个")

        return "；".join(summary_parts) if summary_parts else "发生变化"

    @staticmethod
    def _format_change_summary(event: TriggerEvent) -> str:
        trigger_type = event.trigger_type
        summary = event.change_summary

        if trigger_type == TriggerType.INSTANCE_ADDED.value:
            return f"+ {event.inst_name}"

        if trigger_type == TriggerType.INSTANCE_DELETED.value:
            return f"- {event.inst_name}"

        if trigger_type == TriggerType.RELATION_CHANGE.value:
            return SubscriptionTaskService._format_relation_change_summary(summary)

        return summary

    @staticmethod
    def _format_relation_change_summary(summary: str) -> str:
        model_match = re.search(r"关联模型\[([^\]]+)\]变化", summary)
        if not model_match:
            return summary
        related_model = model_match.group(1)

        added_match = re.search(r"新增关联:\s*(\[[^\]]*\])", summary)
        removed_match = re.search(r"删除关联:\s*(\[[^\]]*\])", summary)

        added_ids = SubscriptionTaskService._parse_relation_ids(added_match.group(1) if added_match else "")
        removed_ids = SubscriptionTaskService._parse_relation_ids(removed_match.group(1) if removed_match else "")

        all_ids = sorted(list(set(added_ids + removed_ids)))
        if not all_ids:
            return summary

        id_name_map = SubscriptionTaskService._get_instance_name_map(related_model, all_ids)
        if not id_name_map:
            return summary

        formatted = summary
        if added_match:
            added_names = [id_name_map.get(inst_id, str(inst_id)) for inst_id in added_ids]
            formatted = re.sub(r"新增关联:\s*\[[^\]]*\]", f"新增关联: [{', '.join(added_names)}]", formatted, count=1,)
        if removed_match:
            removed_names = [id_name_map.get(inst_id, str(inst_id)) for inst_id in removed_ids]
            formatted = re.sub(r"删除关联:\s*\[[^\]]*\]", f"删除关联: [{', '.join(removed_names)}]", formatted, count=1,)
        return formatted

    @staticmethod
    def _parse_relation_ids(ids_expr: str) -> list[int]:
        if not ids_expr:
            return []
        try:
            raw_ids = literal_eval(ids_expr)
        except Exception:
            return []
        if not isinstance(raw_ids, list):
            return []

        parsed_ids: list[int] = []
        for item in raw_ids:
            try:
                parsed_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return parsed_ids

    @staticmethod
    def _get_instance_name_map(model_id: str, instance_ids: list[int]) -> dict[int, str]:
        if not model_id or not instance_ids:
            return {}
        try:
            data, _ = InstanceManage.instance_list(
                model_id=model_id,
                params=[{"field": "id", "type": "id[]", "value": instance_ids}],
                page=1,
                page_size=max(1, len(instance_ids)),
                order="",
                permission_map={},
                creator="",
            )
        except Exception as exc:
            logger.error(
                f"[Subscription] 查询关联实例名称失败 model_id={model_id}, error={exc}", exc_info=True,
            )
            return {}

        name_map: dict[int, str] = {}
        for item in data or []:
            inst_id = item.get("_id")
            if inst_id is None:
                continue
            try:
                int_id = int(inst_id)
            except (TypeError, ValueError):
                continue
            name_map[int_id] = get_inst_display_name(item, int_id)
        return name_map

    @staticmethod
    def _get_trigger_type_display(trigger_type: str) -> str:
        return TRIGGER_TYPE_CHOICES.get(trigger_type, trigger_type)

    @staticmethod
    def _format_triggered_at(triggered_at: str) -> str:
        try:
            dt = datetime.fromisoformat(triggered_at.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return triggered_at

    @staticmethod
    def _get_receivers_from_recipients(system_mgmt_client: SystemMgmt, recipients: dict) -> list:
        users = recipients.get("users", []) if isinstance(recipients, dict) else []
        groups = recipients.get("groups", []) if isinstance(recipients, dict) else []
        all_users = set(users)

        for group_id in groups:
            try:
                result = system_mgmt_client.get_group_users(group_id, include_children=False)
                if isinstance(result, dict) and result.get("result"):
                    for user in result.get("data", []):
                        username = user.get("username")
                        if username:
                            all_users.add(username)
            except Exception as exc:
                logger.error(
                    f"[Subscription] 解析接收组织失败 group_id={group_id}, error={exc}", exc_info=True,
                )

        return list(all_users)
