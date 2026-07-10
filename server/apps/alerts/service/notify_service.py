# -- coding: utf-8 --
# @File: notify_service.py
# @Time: 2025/6/26 15:01
# @Author: windyzhao
import re

from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.alert_operator import NotifyResult
from apps.core.logger import alert_logger as logger


class NotifyResultService(object):

    FAILURE_REASON_MAX_LENGTH = 500
    FAILURE_REASON_FIELDS = ("message", "errmsg", "error", "detail")
    DEFAULT_FAILURE_REASON = "通知失败，渠道未返回具体原因"
    URL_QUERY_PATTERN = re.compile(r"(https?://[^\s?]+)\?[^\s]+", re.IGNORECASE)
    SECRET_PATTERN = re.compile(
        r'''(?i)(["']?\b(?:(?:api|access|refresh)[_-]?)?(?:token|key|secret|password)\b["']?)'''
        r'''(\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&}]+)'''
    )

    def __init__(self, notify_users: list, channel, notify_result: dict, notify_object, notify_action_object="alert"):
        """
        notify_users: 通知的用户列表
        channel: 通知渠道，email, wechat, sms等
        notify_result: 通知结果，成功或失败
        notify_object: 通知的对象，默认为告警 alert, event, incident, system
        """
        self.notify_users = notify_users
        self.channel = channel
        self.notify_result = notify_result
        self.notify_action_object = notify_action_object
        self.notify_object = notify_object

    def format_notify_result(self):
        """
        格式化通知结果
        """
        try:
            if not isinstance(self.notify_result, dict):
                return NotifyResultStatus.FAILED

            result = self.notify_result.get("result")
            if isinstance(result, bool):
                return NotifyResultStatus.SUCCESS if result else NotifyResultStatus.FAILED

            for code_field in ("errcode", "code"):
                if code_field not in self.notify_result:
                    continue
                code = self.notify_result[code_field]
                is_success = str(code).strip() == "0"
                return NotifyResultStatus.SUCCESS if is_success else NotifyResultStatus.FAILED

            # 未知响应结构保留原有兼容行为，避免把历史成功渠道误记为失败。
            return NotifyResultStatus.SUCCESS
        except Exception as e:
            logger.warning(
                "[AlertNotify] NotifyResultService format_notify_result 解析失败, result=%s, error=%s",
                self.notify_result, e,
            )
            return NotifyResultStatus.FAILED

    def format_failure_reason(self):
        """提取可向前端展示的安全失败原因。"""
        if self.format_notify_result() != NotifyResultStatus.FAILED:
            return None

        reason = ""
        if isinstance(self.notify_result, dict):
            for field in self.FAILURE_REASON_FIELDS:
                value = self.notify_result.get(field)
                if value not in (None, ""):
                    reason = str(value)
                    break

        if not reason:
            reason = self.DEFAULT_FAILURE_REASON

        reason = self.URL_QUERY_PATTERN.sub(r"\1?***", reason)
        reason = self.SECRET_PATTERN.sub(r"\1\2***", reason)
        return reason[: self.FAILURE_REASON_MAX_LENGTH]

    def save_notify_result(self):
        """
        保存通知结果到数据库
        """
        status = self.format_notify_result()
        notify_result = NotifyResult(
            notify_people=self.notify_users,
            notify_channel=self.channel,
            notify_result=status,
            failure_reason=self.format_failure_reason(),
            notify_type=self.notify_action_object
        )
        if self.notify_object:
            notify_result.notify_object = self.notify_object

        notify_result.save()
