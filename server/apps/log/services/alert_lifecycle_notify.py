import time
from typing import Any

from apps.core.logger import celery_logger as logger
from apps.log.constants.alert_policy import AlertConstants
from apps.monitor.utils.system_mgmt_api import SystemMgmtUtils
from apps.system_mgmt.models.channel import Channel, ChannelChoices


class LogAlertLifecycleNotifier:
    """将日志告警生命周期转换为告警中心标准 Event 并通过现有渠道发送。"""

    ALERT_CENTER_METHOD = "receive_alert_events"
    LEVEL_TO_ALERT_CENTER = {
        "critical": "0",
        "error": "1",
        "warning": "2",
        "info": "3",
        "no_data": "2",
    }

    def __init__(self, policy):
        self.policy = policy

    def _get_channel(self):
        return Channel.objects.filter(id=self.policy.notice_type_id).first()

    @classmethod
    def _is_alert_center_channel(cls, channel) -> bool:
        return bool(
            channel
            and channel.channel_type == ChannelChoices.NATS
            and (channel.config or {}).get("method_name") == cls.ALERT_CENTER_METHOD
        )

    def is_alert_center_channel(self) -> bool:
        return self._is_alert_center_channel(self._get_channel())

    def _organizations(self) -> list[int]:
        return list(
            self.policy.policyorganization_set.order_by("organization")
            .values_list("organization", flat=True)
            .distinct()
        )

    def _resource_name(self) -> str:
        return self.policy.name

    def _title(self, content: str) -> str:
        return content or self.policy.alert_name

    @staticmethod
    def _timestamp(value) -> str | None:
        return str(int(value.timestamp())) if value else None

    def _level(self, value: str) -> str:
        return self.LEVEL_TO_ALERT_CENTER.get(value, "3")

    def _labels(self, alert, *, include_operator: bool = False) -> dict[str, str]:
        labels = {
            "policy_name": self.policy.name,
            "alert_type": self.policy.alert_type,
            "collect_type_id": str(self.policy.collect_type_id or ""),
            "log_alert_id": str(alert.id),
            "status": alert.status,
        }
        if include_operator:
            labels["operator"] = alert.operator or ""
        return labels

    def build_created_event(self, event) -> dict[str, Any]:
        alert = event.alert
        content = event.content or ""
        # 日志告警没有稳定的指标项、指标值或 CMDB 资源类型，保持空值交由告警中心适配。
        return {
            "external_id": str(event.alert_id),
            "rule_id": str(event.policy_id),
            "title": self._title(content),
            "description": content,
            "level": self._level(event.level),
            "value": None,
            "action": "created",
            "start_time": self._timestamp(event.event_time),
            "end_time": None,
            "item": "",
            "resource_id": event.source_id,
            "resource_type": "",
            "resource_name": self._resource_name(),
            "organizations": self._organizations(),
            "tags": {},
            "labels": self._labels(alert),
        }

    def build_closed_event(self, alert) -> dict[str, Any]:
        content = alert.content or ""
        closed_at = self._timestamp(alert.end_event_time)
        # closed 与 created 使用同一字段契约，避免生命周期事件出现不同的资源语义。
        return {
            "external_id": str(alert.id),
            "rule_id": str(alert.policy_id),
            "title": self._title(content),
            "description": content,
            "level": self._level(alert.level),
            "value": None,
            "action": "closed",
            "start_time": closed_at,
            "end_time": closed_at,
            "item": "",
            "resource_id": alert.source_id,
            "resource_type": "",
            "resource_name": self._resource_name(),
            "organizations": self._organizations(),
            "tags": {},
            "labels": self._labels(alert, include_operator=True),
        }

    @staticmethod
    def _parse_channel_result(send_result):
        if not isinstance(send_result, dict):
            return False, "invalid response"

        if send_result.get("result") is False:
            return (
                False,
                send_result.get("message")
                or send_result.get("errmsg")
                or send_result.get("msg")
                or "Unknown error",
            )

        errcode = send_result.get("errcode")
        if errcode is not None and errcode != 0:
            return (
                False,
                send_result.get("errmsg")
                or send_result.get("msg")
                or send_result.get("message")
                or f"errcode={errcode}",
            )

        code = send_result.get("code")
        if code is not None and code != 0:
            return (
                False,
                send_result.get("msg")
                or send_result.get("message")
                or send_result.get("errmsg")
                or f"code={code}",
            )

        return True, ""

    def _notify(self, event_payload: dict[str, Any], max_attempts=None) -> tuple[bool, dict]:
        channel = self._get_channel()
        if not self._is_alert_center_channel(channel):
            return False, {"result": False, "message": "not an alert-center channel"}

        if max_attempts is None:
            max_attempts = AlertConstants.NOTICE_SEND_MAX_ATTEMPTS
        max_attempts = max(int(max_attempts), 1)
        action = event_payload["action"]
        external_id = event_payload["external_id"]
        envelope = {
            "source_id": "nats",
            "pusher": "lite-log",
            "events": [event_payload],
        }
        last_result = {"result": False, "message": "Unknown error"}

        for attempt in range(1, max_attempts + 1):
            try:
                send_result = SystemMgmtUtils.send_msg_with_channel(
                    channel.id,
                    "",
                    envelope,
                    [],
                )
                success, error_message = self._parse_channel_result(send_result)
                if success:
                    logger.info(
                        "日志告警生命周期推送成功 policy=%s alert=%s action=%s attempt=%s/%s",
                        self.policy.id,
                        external_id,
                        action,
                        attempt,
                        max_attempts,
                    )
                    return True, send_result

                last_result = send_result if isinstance(send_result, dict) else {
                    "result": False,
                    "message": error_message,
                }
                logger.error(
                    "日志告警生命周期推送失败 policy=%s alert=%s action=%s attempt=%s/%s error=%s",
                    self.policy.id,
                    external_id,
                    action,
                    attempt,
                    max_attempts,
                    error_message,
                )
            except Exception as exc:
                last_result = {"result": False, "message": str(exc)}
                logger.error(
                    "日志告警生命周期推送异常 policy=%s alert=%s action=%s attempt=%s/%s error=%s",
                    self.policy.id,
                    external_id,
                    action,
                    attempt,
                    max_attempts,
                    exc,
                    exc_info=True,
                )

            if attempt < max_attempts:
                time.sleep(AlertConstants.NOTICE_SEND_RETRY_BACKOFF_SECONDS * attempt)

        return False, last_result

    def notify_created(self, event, max_attempts=None) -> tuple[bool, dict]:
        return self._notify(self.build_created_event(event), max_attempts=max_attempts)

    def notify_closed(self, alert, max_attempts=None) -> tuple[bool, dict]:
        return self._notify(self.build_closed_event(alert), max_attempts=max_attempts)
