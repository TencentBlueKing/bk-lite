# -- coding: utf-8 --
# @File: un_dispatch.py
# @Time: 2025/6/26 18:45
# @Author: windyzhao
from apps.alerts.common.notify.base import NotifyParamsFormat
from apps.alerts.constants.constants import AlertStatus
from apps.alerts.models.sys_setting import SystemSetting
from apps.alerts.models.models import  Alert


class UnDispatchService:
    """未分派告警通知服务"""

    @staticmethod
    def get_un_dispatch_config():
        """获取未分派告警通知配置"""
        setting = SystemSetting.objects.filter(key="no_dispatch_alert_notice").first()
        if setting and setting.value:
            return setting
        return None

    @staticmethod
    def search_no_operator_alerts():
        """查询未分派的告警"""
        alerts = Alert.objects.filter(status=AlertStatus.UNASSIGNED)
        return list(alerts)

    @classmethod
    def notify_un_dispatched_alert_params_format(cls, alerts=None):
        """通知未分派的告警"""
        result = []
        notify_setting = cls.get_un_dispatch_config()
        if not notify_setting:
            return result
        if alerts is None:
            alerts = cls.search_no_operator_alerts()
        notify_people = notify_setting.value["notify_people"]
        notify_channel = notify_setting.value["notify_channel"]
        if not notify_people or not notify_channel or not alerts:
            return result

        param_format = NotifyParamsFormat(username_list=notify_people, alerts=alerts)
        title = param_format.format_title()
        content = param_format.format_content()
        for channel in notify_channel:
            result.append(
                {"username_list": notify_people,
                 "channel_type": channel["channel_type"],
                 "channel_id": channel["id"],
                 "title": title,
                 "content": content,
                 "object_id": "",
                 "notify_action_object": ""
                 }
            )

        return result
