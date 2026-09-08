import os
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone

from apps.core.logger import monitor_logger as logger
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.system_mgmt.models import Channel, User

DEFAULT_NOTICE_TIMEZONE = "Asia/Shanghai"


ACTION_TO_ALERT_CENTER = {
    "created": "created",
    "upgraded": "created",
    "recovered": "recovery",
    "closed": "closed",
}

LEVEL_TO_ALERT_CENTER = {
    "critical": "0",
    "error": "1",
    "warning": "2",
    "info": "3",
    "no_data": "2",
}

NOTIFY_SCOPE_NONE = "none"
NOTIFY_SCOPE_ALERT_CENTER_ONLY = "alert_center_only"
NOTIFY_SCOPE_ALL_CONFIGURED = "all_configured"
ALERT_CENTER_PER_EVENT_ACK_ENABLED = os.getenv("MONITOR_ALERT_CENTER_PER_EVENT_ACK_ENABLED", "false").lower() in {"1", "true", "yes"}
ALERT_CENTER_ACK_TOKEN = os.getenv("ALERTS_PER_EVENT_ACK_TOKEN", "")
ALERT_CENTER_CREATED_RETRY_ENABLED = os.getenv("MONITOR_ALERT_CENTER_CREATED_RETRY_ENABLED", "false").lower() in {"1", "true", "yes"}


def _policy_secondary_context(policy) -> str:
    """同名策略展示用短上下文：与序列化展示口径对齐（公式展开指标名）。"""
    if not policy:
        return ""
    query = getattr(policy, "query_condition", None) or {}
    if not isinstance(query, dict):
        query = {}
    # 与 PolicyService.display_metric_name 对齐，避免详情/通知公式文案不一致
    from apps.monitor.services.policy import PolicyService

    display = PolicyService.display_metric_name({"query_condition": query})
    if display:
        return display
    monitor_object = getattr(policy, "monitor_object", None)
    if monitor_object is not None:
        return str(getattr(monitor_object, "display_name", None) or getattr(monitor_object, "name", "") or "").strip()
    return ""


def _format_policy_display_label(policy) -> str:
    if not policy:
        return ""
    name = str(getattr(policy, "name", "") or "").strip()
    secondary = _policy_secondary_context(policy)
    if name and secondary:
        return f"{name}（{secondary}）"
    return name or secondary


class AlertLifecycleNotifier:
    def __init__(self, policy=None, policies_by_id=None):
        self.policy = policy
        self.policies_by_id = policies_by_id or {}

    def notify_alerts(self, alerts, action, operator="", reason="", notify_scope=NOTIFY_SCOPE_ALL_CONFIGURED):
        if not alerts:
            return

        if notify_scope == NOTIFY_SCOPE_NONE:
            self._reset_alert_center_flags(alerts)
            return

        # created 在扫描事务内先落 outbox；其余生命周期调用方仍保留 legacy pending
        # 标志，由这里幂等补齐不可变意图。回滚可关闭 outbox 并继续使用旧链路。
        self.enqueue_alert_center_deliveries(alerts, action, operator=operator, reason=reason)

        alert_log_entries = defaultdict(list)

        groups = defaultdict(list)
        for alert in alerts:
            channel_ids = self._resolve_notice_type_ids(alert)
            notice_users = self._resolve_notice_users(alert)
            if not channel_ids:
                logger.warning(f"Alert {alert.id} has no notice_type_ids configured, skip notification")
                continue
            for channel_id in channel_ids:
                channel = Channel.objects.filter(id=channel_id).first()
                if not self._should_notify_channel(alert, channel, channel_id, action, notify_scope):
                    continue
                groups[(channel_id, tuple(notice_users) if notice_users else ())].append(alert)

        alert_center_results = defaultdict(list)

        for (channel_id, notice_users_tuple), group_alerts in groups.items():
            notice_users = list(notice_users_tuple)
            try:
                # 灰度期间保留 legacy 即时投递；outbox 使用稳定 payload 身份，
                # receiver 会把响应丢失后的双投收敛为 duplicate。关闭开关即可回滚。
                results = self._send_to_channel(channel_id, notice_users, group_alerts, action, operator, reason, notify_scope)
                for alert, log_entry in results:
                    alert_log_entries[alert.id].append(log_entry)
                    if log_entry.get("is_alert_center"):
                        alert_center_results[alert.id].append(bool(log_entry.get("success")))
            except Exception as e:
                logger.error(
                    f"Lifecycle notify exception: action={action}, channel_id={channel_id}, error={e}",
                    exc_info=True,
                )
                now = datetime.now(timezone.utc).isoformat()
                for alert in group_alerts:
                    alert_log_entries[alert.id].append(
                        {
                            "time": now,
                            "action": action,
                            "channel_id": channel_id,
                            "success": False,
                            "error": str(e),
                        }
                    )
                # 异常时无法确认是否为 NATS 渠道，保守地标记为已命中，避免误清 notified 标志
                try:
                    exc_channel = Channel.objects.filter(id=channel_id).first()
                    if exc_channel and exc_channel.channel_type == "nats" and exc_channel.config.get("method_name") == "receive_alert_events":
                        for alert in group_alerts:
                            alert_center_results[alert.id].append(False)
                except Exception:
                    for alert in group_alerts:
                        alert_center_results[alert.id].append(False)

        self._persist_notice_logs(alerts, alert_log_entries)
        alert_center_success_ids = {alert_id for alert_id, results in alert_center_results.items() if results and all(results)}
        if alert_center_success_ids:
            self._mark_alert_center_notified(alert_center_success_ids)

        # 未经过 NATS 推送路径的告警（无告警中心渠道）：归还 notified=True，避免补偿任务空转
        not_targeted_ids = {a.id for a in alerts} - set(alert_center_results)
        if not_targeted_ids:
            self._reset_alert_center_flags_by_ids(not_targeted_ids)

    def _mark_alert_center_notified(self, alert_ids):
        if not alert_ids:
            return
        from apps.monitor.models import MonitorAlert

        # 直接按 id 原子更新，避免重新 SELECT 已在内存中的对象
        MonitorAlert.objects.filter(id__in=list(alert_ids)).update(alert_center_notified=True, alert_center_retry_count=0)

    def _reset_alert_center_flags(self, alerts):
        """通知被跳过（policy.notice=False 等），将预设的 notified=False 归还为 True"""
        if not alerts:
            return
        from apps.monitor.models import MonitorAlert

        MonitorAlert.objects.filter(id__in=[a.id for a in alerts], alert_center_notified=False).update(alert_center_notified=True)

    def _reset_alert_center_flags_by_ids(self, alert_ids):
        """告警未经过 NATS 推送路径，将预设的 notified=False 归还为 True"""
        if not alert_ids:
            return
        from apps.monitor.models import MonitorAlert

        MonitorAlert.objects.filter(id__in=alert_ids, alert_center_notified=False).update(alert_center_notified=True)

    def push_to_alert_center_only(self, alerts, action, operator="", reason=""):
        """专用于告警中心补偿通知，跳过 IM 通知直接推送到 NATS 告警中心"""
        channel_ids = {int(value) for alert in alerts for value in self._resolve_notice_type_ids(alert) if str(value).isdigit()}
        channels = set()
        for channel_id in channel_ids:
            try:
                capability = SystemMgmtUtils.probe_notification_channel(channel_id, capability_only=True) or {}
            except Exception:
                logger.exception("告警中心补偿渠道能力查询失败: channel_id=%s", channel_id)
                continue
            if capability.get("delivery_mode") == "alert_event_copy":
                channels.add(channel_id)
        groups = defaultdict(list)
        for alert in alerts:
            for value in self._resolve_notice_type_ids(alert):
                if str(value).isdigit() and int(value) in channels:
                    groups[int(value)].append(alert)
        push_results = []
        delivered_alert_ids = set()
        for channel_id, group_alerts in groups.items():
            results = self._push_to_alert_center(
                channel_id,
                str(channel_id),
                group_alerts,
                action,
                operator,
                reason,
            )
            push_results.extend(results)
            delivered_alert_ids.update(alert.id for alert, _ in results)
        push_results.extend(
            (alert, {"success": False, "error": "alert_center_channel_not_configured"}) for alert in alerts if alert.id not in delivered_alert_ids
        )
        # 写入 notice_logs，与即时层保持一致
        alert_log_entries = defaultdict(list)
        for alert, log_entry in push_results:
            alert_log_entries[alert.id].append(log_entry)
        self._persist_notice_logs(alerts, alert_log_entries)
        results_by_alert = defaultdict(list)
        for alert, log_entry in push_results:
            results_by_alert[alert.id].append(bool(log_entry.get("success")))
        return [(alert, bool(results_by_alert[alert.id]) and all(results_by_alert[alert.id])) for alert in alerts]

    def enqueue_alert_center_deliveries(self, alerts, action, operator="", reason=""):
        from apps.monitor.services.alert_center_delivery import enqueue_alert_center_deliveries

        return enqueue_alert_center_deliveries(
            alerts,
            action,
            notifier=self,
            operator=operator,
            reason=reason,
        )

    def _persist_notice_logs(self, alerts, alert_log_entries):
        if not alert_log_entries:
            return
        from apps.monitor.models import MonitorAlert

        alerts_to_update = []
        for alert in alerts:
            entries = alert_log_entries.get(alert.id)
            if not entries:
                continue
            alert.notice_logs = (alert.notice_logs or []) + entries
            alerts_to_update.append(alert)

        if alerts_to_update:
            MonitorAlert.objects.bulk_update(alerts_to_update, fields=["notice_logs"])

    def _resolve_notice_type_ids(self, alert):
        if alert.notice_type_ids:
            return alert.notice_type_ids
        if self.policy and getattr(self.policy, "notice", False) and getattr(self.policy, "notice_type_ids", None):
            return self.policy.notice_type_ids
        return []

    def _resolve_notice_users(self, alert):
        if alert.notice_users:
            return alert.notice_users
        if self.policy and getattr(self.policy, "notice_users", None):
            return self.policy.notice_users
        return []

    def _should_notify_channel(self, alert, channel, channel_id, action, notify_scope):
        is_alert_center = self._is_alert_center_channel(channel)
        if notify_scope == NOTIFY_SCOPE_ALERT_CENTER_ONLY and not is_alert_center:
            return False

        if not self.policy or self.policy.notice:
            return True

        if action == "created":
            return False

        if not channel or not self._has_successful_created_notice(alert, channel_id):
            return False

        if action == "upgraded":
            return is_alert_center

        return action in {"recovered", "closed"}

    def _has_successful_created_notice(self, alert, channel_id):
        for log_entry in alert.notice_logs or []:
            if not isinstance(log_entry, dict):
                continue
            if log_entry.get("action") != "created":
                continue
            if str(log_entry.get("channel_id")) != str(channel_id):
                continue
            if log_entry.get("success") is True:
                return True
        return False

    def _send_to_channel(self, channel_id, notice_users, alerts, action, operator, reason, notify_scope):
        channel = Channel.objects.filter(id=channel_id).first()
        if not channel:
            logger.warning(f"Channel {channel_id} not found, skip notification for {len(alerts)} alerts")
            now = datetime.now(timezone.utc).isoformat()
            return [
                (alert, {"time": now, "action": action, "channel_id": channel_id, "success": False, "error": "channel_not_found"}) for alert in alerts
            ]

        is_alert_center = self._is_alert_center_channel(channel)
        if notify_scope == NOTIFY_SCOPE_ALERT_CENTER_ONLY and not is_alert_center:
            logger.info(f"Skip non-alert-center channel {channel_id} for alert-center-only lifecycle notify")
            return []

        channel_name = channel.name or str(channel_id)

        if is_alert_center:
            from apps.monitor.services.alert_center_delivery import ALERT_CENTER_OUTBOX_DELIVERY_ENABLED, ALERT_CENTER_OUTBOX_ENABLED

            if ALERT_CENTER_OUTBOX_ENABLED and ALERT_CENTER_OUTBOX_DELIVERY_ENABLED:
                # active 阶段由持久化 outbox 独占告警中心投递；普通 IM 渠道仍走旧链路。
                now = datetime.now(timezone.utc).isoformat()
                return [
                    (
                        alert,
                        {
                            "time": now,
                            "action": action,
                            "channel_id": channel_id,
                            "channel_name": channel_name,
                            "is_alert_center": True,
                            "success": False,
                            "error": "outbox_pending",
                        },
                    )
                    for alert in alerts
                ]
            return self._push_to_alert_center(channel_id, channel_name, alerts, action, operator, reason)
        else:
            return self._send_normal_notice(channel_id, channel_name, notice_users, alerts, action, operator, reason)

    def _is_alert_center_channel(self, channel):
        return bool(channel and channel.channel_type == "nats" and channel.config.get("method_name") == "receive_alert_events")

    @staticmethod
    def _parse_channel_result(send_result):
        """Normalize channel send result into (success, error_message).

        Handles both the normalized contract (``result: False``) and raw bot
        API responses that carry ``errcode``/``code`` without a ``result`` field.
        """
        if not isinstance(send_result, dict):
            return False, "invalid response"

        # Explicit normalized failure
        if send_result.get("result") is False:
            error = send_result.get("message") or send_result.get("errmsg") or send_result.get("msg") or "Unknown error"
            return False, error

        # Raw bot-style failure: errcode != 0 (WeCom/DingTalk)
        errcode = send_result.get("errcode")
        if errcode is not None and errcode != 0:
            error = send_result.get("errmsg") or send_result.get("msg") or send_result.get("message") or f"errcode={errcode}"
            return False, error

        # Raw bot-style failure: code != 0 (Feishu)
        code = send_result.get("code")
        if code is not None and code != 0:
            error = send_result.get("msg") or send_result.get("message") or send_result.get("errmsg") or f"code={code}"
            return False, error

        return True, ""

    def _send_normal_notice(self, channel_id, channel_name, notice_users, alerts, action, operator, reason):
        results = []
        target_timezone = self._resolve_notice_timezone(notice_users)
        for alert in alerts:
            now = datetime.now(timezone.utc).isoformat()
            title = self._build_title(alert, action)
            content = self._build_content(alert, action, operator, reason, target_timezone=target_timezone)
            try:
                send_result = SystemMgmtUtils.send_msg_with_channel(channel_id, title, content, notice_users)
                success, error_msg = self._parse_channel_result(send_result)
                log_entry = {"time": now, "action": action, "channel_id": channel_id, "channel_name": channel_name, "success": success}
                if not success:
                    log_entry["error"] = error_msg
                    logger.error(f"Normal notify failed: alert={alert.id}, action={action}, message={error_msg}")
                else:
                    logger.info(f"Normal notify success: alert={alert.id}, action={action}")
                results.append((alert, log_entry))
            except Exception as e:
                logger.error(f"Normal notify exception: alert={alert.id}, action={action}, error={e}", exc_info=True)
                results.append(
                    (
                        alert,
                        {"time": now, "action": action, "channel_id": channel_id, "channel_name": channel_name, "success": False, "error": str(e)},
                    )
                )
        return results

    def _push_to_alert_center(self, channel_id, channel_name, alerts, action, operator, reason):
        now = datetime.now(timezone.utc).isoformat()
        instance_org_map = self._build_instance_org_map(alerts)
        monitor_identity_map = self._build_monitor_identity_map(alerts)
        payloads = [
            self._build_alert_center_payload(
                alert,
                action,
                operator,
                reason,
                instance_org_map,
                monitor_identity_map,
            )
            for alert in alerts
        ]
        # shadow 阶段先写 outbox、仍由 legacy 实发。两条路径必须共享同一代次身份，
        # 这样切到 active 后重放 pending 只会得到 duplicate，不会重复建事件。
        from apps.monitor.models import MonitorAlertCenterDelivery
        from apps.monitor.services.alert_center_delivery import ALERT_CENTER_OUTBOX_ENABLED

        use_per_event_ack = ALERT_CENTER_PER_EVENT_ACK_ENABLED or ALERT_CENTER_OUTBOX_ENABLED
        delivery_ids = {}
        if not ALERT_CENTER_OUTBOX_ENABLED and not use_per_event_ack:
            # 两个扩展开关均关闭时严格保留历史 NATS payload；旧接收端无需
            # 理解 lifecycle 字段即可继续工作。
            for payload in payloads:
                payload.pop("lifecycle_action", None)
        if ALERT_CENTER_OUTBOX_ENABLED:
            rows = (
                MonitorAlertCenterDelivery.objects.filter(
                    alert_id__in=[alert.id for alert in alerts],
                    action=action,
                    channel_id=channel_id,
                )
                .order_by("alert_id", "-generation")
                .values_list("alert_id", "delivery_id")
            )
            for alert_id, delivery_id in rows:
                delivery_ids.setdefault(alert_id, delivery_id)
            for alert, payload in zip(alerts, payloads):
                if alert.id in delivery_ids:
                    payload["lifecycle_generation"] = delivery_ids[alert.id]
        if use_per_event_ack:
            for alert, payload in zip(alerts, payloads):
                payload["delivery_id"] = delivery_ids.get(alert.id, self._build_delivery_id(alert, action))
                payload.setdefault("lifecycle_generation", payload["delivery_id"])
        content = {
            "source_id": "nats",
            "pusher": "lite-monitor",
            "events": payloads,
        }
        if use_per_event_ack:
            content["ack_mode"] = "per_event_v1"
            content["ack_token"] = ALERT_CENTER_ACK_TOKEN
        success = False
        error_msg = ""
        event_results = {}
        try:
            send_result = SystemMgmtUtils.send_msg_with_channel(channel_id, "", content, [], internal_caller="lite-monitor")
            success, error_msg = self._parse_channel_result(send_result)
            if use_per_event_ack and isinstance(send_result, dict):
                details = send_result.get("data") or {}
                event_results = {
                    item.get("delivery_id"): item for item in details.get("event_results") or [] if isinstance(item, dict) and item.get("delivery_id")
                }
            if success:
                logger.info(f"Lifecycle push to alert center success: action={action}, count={len(alerts)}")
            else:
                logger.error(f"Lifecycle push to alert center failed: action={action}, count={len(alerts)}, message={error_msg}")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Lifecycle push to alert center exception: action={action}, error={e}", exc_info=True)

        results = []
        for alert in alerts:
            alert_success = success
            alert_error = error_msg
            if event_results:
                ack = event_results.get(
                    delivery_ids.get(alert.id, self._build_delivery_id(alert, action)),
                    {},
                )
                alert_success = ack.get("status") in {"accepted", "duplicate"}
                if not alert_success:
                    alert_error = ack.get("status") or "missing per-event acknowledgement"
                    if ack:
                        alert_error = f"{alert_error} (retryable={bool(ack.get('retryable'))})"
            log_entry = {
                "time": now,
                "action": action,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "is_alert_center": True,
                "success": alert_success,
            }
            if not alert_success:
                log_entry["error"] = alert_error
            results.append((alert, log_entry))
        return results

    @staticmethod
    def _build_delivery_id(alert, action):
        """旧链路的 ACK 关联键；未来 outbox 可直接替换为其持久化 generation key。"""
        return ":".join(
            str(value or "")
            for value in (
                alert.id,
                action,
                getattr(alert, "start_event_time", None),
                getattr(alert, "end_event_time", None),
                getattr(alert, "level", None),
                getattr(alert, "value", None),
            )
        )

    def _build_instance_org_map(self, alerts):
        """按本批告警的实例一次性查出 实例ID -> [组织id] 映射，避免逐条 N+1 查询。"""
        instance_ids = {alert.monitor_instance_id for alert in alerts if alert.monitor_instance_id}
        if not instance_ids:
            return {}
        from apps.monitor.models.monitor_object import MonitorInstanceOrganization

        org_map = defaultdict(list)
        rows = MonitorInstanceOrganization.objects.filter(monitor_instance_id__in=instance_ids).values_list("monitor_instance_id", "organization")
        for instance_id, organization in rows:
            org_map[instance_id].append(organization)
        return org_map

    @staticmethod
    def _build_monitor_identity_map(alerts):
        """按本批告警一次性读取发送时的监控实例身份快照。"""
        instance_ids = {alert.monitor_instance_id for alert in alerts if alert.monitor_instance_id}
        if not instance_ids:
            return {}

        from apps.monitor.models.monitor_object import MonitorInstance

        return {
            instance.id: {
                "cmdb_id": instance.cmdb_id,
                "resource_type": instance.monitor_object.name,
            }
            for instance in MonitorInstance.objects.select_related("monitor_object").filter(id__in=instance_ids)
        }

    def _resolve_alert_organizations(self, alert, instance_org_map, policy=None):
        """实例组织优先；实例无组织时回退策略组织；都没有则为空。"""
        organizations = instance_org_map.get(alert.monitor_instance_id)
        if organizations:
            return organizations
        policy = policy or self.policy
        if policy and getattr(policy, "organizations", None):
            return list(policy.organizations)
        return []

    def _build_alert_center_payload(
        self,
        alert,
        action,
        operator,
        reason,
        instance_org_map=None,
        monitor_identity_map=None,
    ):
        instance_org_map = instance_org_map or {}
        monitor_identity_map = monitor_identity_map or {}
        policy = self.policy
        if action == "created":
            policy = self.policies_by_id.get(alert.policy_id, policy)
        monitor_identity = monitor_identity_map.get(
            alert.monitor_instance_id,
            {},
        )
        policy_monitor_object = getattr(policy, "monitor_object", None)
        alert_center_action = ACTION_TO_ALERT_CENTER.get(action, "created")
        start_time = str(int(alert.start_event_time.timestamp())) if alert.start_event_time else None
        end_time = str(int(alert.end_event_time.timestamp())) if alert.end_event_time else None
        return {
            "external_id": str(alert.id),
            "rule_id": str(alert.policy_id),
            "title": alert.content,
            "description": alert.content,
            "level": LEVEL_TO_ALERT_CENTER.get(alert.level, "3"),
            "value": float(alert.value) if alert.value is not None else None,
            "action": alert_center_action,
            # 接收端用该字段区分同一业务 action 的生命周期代次；旧接收端忽略未知字段。
            "lifecycle_action": action,
            "start_time": start_time,
            "end_time": end_time,
            "monitor_id": alert.monitor_instance_id,
            "cmdb_id": monitor_identity.get("cmdb_id"),
            "resource_id": alert.monitor_instance_id,
            "resource_type": monitor_identity.get("resource_type") or getattr(policy_monitor_object, "name", ""),
            "resource_name": getattr(alert, "monitor_instance_name", ""),
            "organizations": self._resolve_alert_organizations(alert, instance_org_map, policy),
            "tags": getattr(alert, "dimensions", {}),
            "labels": {
                "policy_name": _format_policy_display_label(policy),
                "metric_instance_id": getattr(alert, "metric_instance_id", ""),
                "operator": operator,
                "reason": reason,
                "status": alert.status,
            },
        }

    def _build_title(self, alert, action):
        action_labels = {
            "created": "告警产生",
            "upgraded": "告警升级",
            "closed": "告警关闭",
            "recovered": "告警恢复",
        }
        label = action_labels.get(action, "告警通知")
        policy = self.policies_by_id.get(alert.policy_id, self.policy)
        policy_label = _format_policy_display_label(policy)
        return f"{label}：{policy_label}" if policy_label else label

    def _resolve_notice_timezone(self, notice_users):
        """取第一个通知人的账号时区；查不到或列表为空时回退 Asia/Shanghai。"""
        if not notice_users:
            return DEFAULT_NOTICE_TIMEZONE
        try:
            user = User.objects.filter(username__in=list(notice_users)).first()
        except Exception:
            logger.warning("Failed to resolve notice timezone for users=%s", notice_users, exc_info=True)
            return DEFAULT_NOTICE_TIMEZONE
        tz_name = getattr(user, "timezone", None) if user else None
        return tz_name or DEFAULT_NOTICE_TIMEZONE

    @staticmethod
    def _coerce_notice_timezone(target_timezone):
        if isinstance(target_timezone, str) and target_timezone:
            try:
                return ZoneInfo(target_timezone)
            except Exception:
                logger.warning(
                    "Invalid notice timezone %s, fallback to %s",
                    target_timezone,
                    DEFAULT_NOTICE_TIMEZONE,
                )
        elif target_timezone is not None and not isinstance(target_timezone, str):
            return target_timezone
        return ZoneInfo(DEFAULT_NOTICE_TIMEZONE)

    def _format_notice_time(self, dt, target_timezone=None):
        if not dt:
            return ""
        tz = self._coerce_notice_timezone(target_timezone)
        if dj_timezone.is_naive(dt):
            dt = dt.replace(tzinfo=timezone.utc)
        return dj_timezone.localtime(dt, tz).strftime("%Y-%m-%d %H:%M:%S")

    def _build_content(self, alert, action, operator, reason, target_timezone=None):
        parts = [f"告警内容：{alert.content}"]

        instance_name = getattr(alert, "monitor_instance_name", "") or alert.monitor_instance_id
        if instance_name:
            parts.append(f"资源：{instance_name}")

        parts.append(f"级别：{alert.level}")

        if action == "upgraded":
            parts.append("状态：告警级别已升级")
        elif action == "closed":
            if operator:
                parts.append(f"操作人：{operator}")
            if reason:
                parts.append(f"原因：{reason}")
        elif action == "recovered":
            parts.append("状态：已自动恢复")

        if alert.start_event_time:
            parts.append(f"开始时间：{self._format_notice_time(alert.start_event_time, target_timezone)}")

        return "\n".join(parts)
