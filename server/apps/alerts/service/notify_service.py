# -- coding: utf-8 --
# @File: notify_service.py
# @Time: 2025/6/26 15:01
# @Author: windyzhao
from apps.alerts.constants.constants import NotifyResultStatus
from apps.alerts.models.alert_operator import NotifyResult
from apps.core.logger import alert_logger as logger


class NotifyResultService(object):

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
            status = self.notify_result.get("result", False)
            if status:
                return NotifyResultStatus.SUCCESS
            else:
                return NotifyResultStatus.FAILED
        except Exception as e:
            logger.warning("==== NotifyResultService format_notify_result error ===, result={}, error={}".format(
                self.notify_result, e))
            return NotifyResultStatus.FAILED

    def save_notify_result(self):
        """
        保存通知结果到数据库
        """
        notify_result = NotifyResult(
            notify_people=self.notify_users,
            notify_channel=self.channel,
            notify_result=self.format_notify_result(),
            notify_type=self.notify_action_object
        )
        if self.notify_object:
            notify_result.notify_object = self.notify_object

        notify_result.save()
