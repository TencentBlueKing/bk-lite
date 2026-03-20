import re
from ast import literal_eval
from datetime import datetime
from typing import Any

from django.core.cache import cache
from django.utils import timezone

from apps.cmdb.constants.subscription import (
    NOTIFICATION_MAX_DISPLAY_INSTANCES,
    SEND_LOCK_TIMEOUT,
    TRIGGER_TYPE_CHOICES,
    TriggerType,
)
from apps.cmdb.models.subscription_rule import SubscriptionRule
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.subscription_trigger import (
    SubscriptionTriggerService,
    TriggerEvent,
)
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
    - check_rules 由 Celery Beat 定时调度，检测完成后异步派发 send_notifications
    - send_notifications 使用分布式锁防止同一批事件重复发送

    锁设计说明：
    - 使用固定前缀锁（不含时间戳），确保同一时刻仅一个任务实例执行
    - 锁超时设为 SEND_LOCK_TIMEOUT 秒，任务完成后主动释放
    """

    SEND_TASK_NAME = "apps.cmdb.tasks.celery_tasks.send_subscription_notifications"
    SEND_LOCK_KEY = "cmdb:sub_notify_lock:sending"

    @classmethod
    def check_rules(cls) -> None:
        # 定时入口：逐条规则执行触发检测，并将事件直接派发给异步发送任务。
        logger.info("[Subscription] 开始检查订阅规则")
        rules = SubscriptionRule.objects.filter(is_enabled=True)
        count = rules.count()
        queued_event_groups: list[dict[str, Any]] = []
        logger.info(f"[Subscription] 共 {count} 条启用规则")
        if not count:
            logger.info("[Subscription] 没有启用的订阅规则，跳过检查")
            return
        for rule in rules:
            try:
                logger.info(
                    f"[Subscription] 处理规则 rule_id={rule.id}, name={rule.name}"
                )
                service = SubscriptionTriggerService(rule)
                events = service.process()
                logger.info(
                    "[Subscription] 规则检测完成 "
                    f"rule_id={rule.id}, events_count={len(events)}"
                )
                if not events:
                    continue

                queued_event_groups.extend(cls._build_event_groups(events))
                for event in events:
                    logger.info(
                        f"[Subscription] 检测到触发事件 rule_id={rule.id}, trigger_type={event.trigger_type}"
                    )
            except Exception as exc:
                logger.error(
                    f"[Subscription] 处理规则失败 rule_id={rule.id}, error={exc}",
                    exc_info=True,
                )
        if queued_event_groups:
            cls._dispatch_send_notifications_async(
                source="check_rules", event_groups=queued_event_groups
            )
        else:
            logger.info("[Subscription] 本轮无触发事件，跳过异步发送派发")
        logger.info("[Subscription] 订阅规则检查完成")

    @classmethod
    def send_notifications(
        cls, event_groups: list[dict[str, Any]] | None = None
    ) -> None:
        """
        发送订阅通知入口。

        接收异步任务传入的事件组，逐组构建通知内容并发送到指定渠道。
        使用分布式锁防止并发重复发送。

        Args:
            event_groups: 事件组列表，每组包含 rule_id、trigger_type 和 events
        """
        if not cache.add(cls.SEND_LOCK_KEY, 1, timeout=SEND_LOCK_TIMEOUT):
            logger.info(
                "[Subscription] 发送任务已有实例执行中，跳过本次执行"
            )
            return

        logger.info("[Subscription] 开始发送订阅通知")
        if not event_groups:
            logger.info("[Subscription] 未收到异步事件参数，跳过本次发送")
            cache.delete(cls.SEND_LOCK_KEY)
            return

        try:
            logger.info(
                "[Subscription] 接收到异步事件组 "
                f"group_count={len(event_groups)}"
            )

            system_mgmt_client = SystemMgmt()

            for group in event_groups:
                cls._process_single_event_group(group, system_mgmt_client)

            logger.info("[Subscription] 订阅通知发送完成")
        finally:
            cache.delete(cls.SEND_LOCK_KEY)

    @classmethod
    def _process_single_event_group(
        cls, group: dict[str, Any], system_mgmt_client: SystemMgmt
    ) -> None:
        """
        处理单个事件组的通知发送。

        Args:
            group: 事件组字典，包含 events 列表
            system_mgmt_client: SystemMgmt RPC 客户端
        """
        try:
            events = cls._decode_event_dicts(group.get("events", []))
            if not events:
                logger.info("[Subscription] 事件组无有效事件，跳过发送")
                return

            rule_id = events[0].rule_id
            trigger_type = group.get("trigger_type")
            sample_inst_ids = [event.inst_id for event in events[:5]]
            logger.info(
                "[Subscription] 开始处理事件组 "
                f"rule_id={rule_id}, trigger_type={trigger_type}, "
                f"event_count={len(events)}, sample_inst_ids={sample_inst_ids}"
            )

            rule = SubscriptionRule.objects.filter(
                id=rule_id, is_enabled=True
            ).first()
            if not rule:
                logger.info(
                    f"[Subscription] 规则不存在或已停用，跳过发送 rule_id={rule_id}"
                )
                return

            title, content = cls._build_notification_content(rule, events)
            receivers = cls._get_receivers_from_recipients(
                system_mgmt_client, rule.recipients
            )
            logger.info(
                "[Subscription] 准备发送通知 "
                f"rule_id={rule_id}, trigger_type={trigger_type}, "
                f"channels={len(rule.channel_ids)}, receivers={len(receivers)}, "
                f"events_count={len(events)}"
            )

            for channel_id in rule.channel_ids:
                result = system_mgmt_client.send_msg_with_channel(
                    channel_id=channel_id,
                    title=title,
                    content=content,
                    receivers=receivers,
                )
                if not isinstance(result, dict) or not result.get("result"):
                    logger.error(
                        f"[Subscription] 通知发送失败 rule_id={rule_id}, "
                        f"channel_id={channel_id}, "
                        f"error={result.get('message') if isinstance(result, dict) else 'invalid rpc result'}"
                    )
                else:
                    logger.info(
                        f"[Subscription] 通知发送成功 rule_id={rule_id}, "
                        f"channel_id={channel_id}, events_count={len(events)}"
                    )
        except Exception as exc:
            logger.error(
                f"[Subscription] 事件组处理失败 event_group={group}, error={exc}",
                exc_info=True,
            )

    @classmethod
    def _dispatch_send_notifications_async(
        cls, source: str, event_groups: list[dict[str, Any]]
    ) -> None:
        try:
            from apps.core.celery import app

            app.send_task(
                cls.SEND_TASK_NAME,
                kwargs={"event_groups": event_groups},
            )
            logger.info(
                "[Subscription] 异步派发通知发送成功 "
                f"source={source}, task={cls.SEND_TASK_NAME}, group_count={len(event_groups)}"
            )
        except Exception as exc:
            logger.error(
                f"[Subscription] 异步派发通知发送失败 source={source}, error={exc}",
                exc_info=True,
            )

    @staticmethod
    def _build_event_groups(events: list[TriggerEvent]) -> list[dict[str, Any]]:
        grouped_events: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for event in events:
            group_key = (event.rule_id, event.trigger_type)
            grouped_events.setdefault(group_key, []).append(event.to_dict())

        event_groups = [
            {
                "rule_id": rule_id,
                "trigger_type": trigger_type,
                "events": group_events,
            }
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
                logger.warning(
                    f"[Subscription] 事件解码失败，已跳过 item={item}, error={exc}"
                )
                continue
        return events

    @staticmethod
    def _build_notification_content(
        rule: SubscriptionRule, events: list[TriggerEvent]
    ) -> tuple[str, str]:
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
            content_lines.append(
                f"触发类型：{SubscriptionTaskService._get_trigger_type_display(trigger_type)}"
            )

            if trigger_type == TriggerType.EXPIRATION.value:
                content_lines.append(
                    f"到期信息：{SubscriptionTaskService._format_change_summary(event)}"
                )
            else:
                content_lines.append(
                    f"变化摘要：{SubscriptionTaskService._format_change_summary(event)}"
                )

            content_lines.append(
                f"触发时间：{SubscriptionTaskService._format_triggered_at(event.triggered_at)}"
            )
        else:
            content_lines.append(
                f"触发类型：{SubscriptionTaskService._get_trigger_type_display(trigger_type)}"
            )

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
        logger.debug(
            f"[Subscription] 构建通知内容 title={title}, events_count={event_count}"
        )
        return title, content

    @staticmethod
    def _build_title(
        model_name: str, events: list[TriggerEvent], trigger_type: str
    ) -> str:
        event_count = len(events)

        type_display_map = {
            TriggerType.ATTRIBUTE_CHANGE.value: ("属性变化", "个实例属性变化"),
            TriggerType.RELATION_CHANGE.value: ("关联对象变化", "个实例关联对象变化"),
            TriggerType.EXPIRATION.value: ("临近到期提醒", "个实例临近到期提醒"),
            TriggerType.INSTANCE_ADDED.value: ("出现新增实例", "个新增实例"),
            TriggerType.INSTANCE_DELETED.value: ("已删除", "个实例已删除"),
        }

        single_suffix, multi_suffix = type_display_map.get(
            trigger_type, ("变化", "个实例变化")
        )

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

        added_ids = SubscriptionTaskService._parse_relation_ids(
            added_match.group(1) if added_match else ""
        )
        removed_ids = SubscriptionTaskService._parse_relation_ids(
            removed_match.group(1) if removed_match else ""
        )

        all_ids = sorted(list(set(added_ids + removed_ids)))
        if not all_ids:
            return summary

        id_name_map = SubscriptionTaskService._get_instance_name_map(related_model, all_ids)
        if not id_name_map:
            return summary

        formatted = summary
        if added_match:
            added_names = [id_name_map.get(inst_id, str(inst_id)) for inst_id in added_ids]
            formatted = re.sub(
                r"新增关联:\s*\[[^\]]*\]",
                f"新增关联: [{', '.join(added_names)}]",
                formatted,
                count=1,
            )
        if removed_match:
            removed_names = [id_name_map.get(inst_id, str(inst_id)) for inst_id in removed_ids]
            formatted = re.sub(
                r"删除关联:\s*\[[^\]]*\]",
                f"删除关联: [{', '.join(removed_names)}]",
                formatted,
                count=1,
            )
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
                f"[Subscription] 查询关联实例名称失败 model_id={model_id}, error={exc}",
                exc_info=True,
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
    def _get_receivers_from_recipients(
        system_mgmt_client: SystemMgmt, recipients: dict
    ) -> list:
        users = recipients.get("users", []) if isinstance(recipients, dict) else []
        groups = recipients.get("groups", []) if isinstance(recipients, dict) else []
        all_users = set(users)

        for group_id in groups:
            try:
                result = system_mgmt_client.get_group_users(
                    group_id, include_children=False
                )
                if isinstance(result, dict) and result.get("result"):
                    for user in result.get("data", []):
                        username = user.get("username")
                        if username:
                            all_users.add(username)
            except Exception as exc:
                logger.error(
                    f"[Subscription] 解析接收组织失败 group_id={group_id}, error={exc}",
                    exc_info=True,
                )

        return list(all_users)
