# -- coding: utf-8 --
# @File: base.py
# @Time: 2025/6/11 14:06
# @Author: windyzhao
from apps.alerts.constants.constants import LevelType
from apps.alerts.models.models import Level
from apps.system_mgmt.models import User


class NotifyParamsFormat(object):
    """
    NotifyParamsFormat class for formatting notification parameters.
    This class should be extended by specific notification handlers.
    """

    def __init__(self, username_list, alerts: list, build_in: bool = True):
        """
        username_list: 通知用户列表
        alert: Alert object containing alert details
        build_in: 是否内置模版
        """
        self.alerts = alerts
        self.username_list = username_list
        self.user_timezone = self.get_user_timezone()
        self.build_in = build_in

    def get_user_timezone(self):
        # 获取用户时区的逻辑，可以根据实际情况进行调整
        # 例如，可以从用户信息中获取时区设置，或者使用默认时区
        user = User.objects.filter(username__in=self.username_list).first()
        return user.timezone if user else None

    def format_title(self):
        if self.build_in:
            alert = self.alerts[0]
            level = Level.objects.get(level_type=LevelType.ALERT, level_id=int(alert.level))
            title = f"【{level.level_display_name}】{alert.title}"
        else:
            title = f"系统有{len(self.alerts)}条告警未分派，请及时处理"
        return title

    def format_content(self):
        content = ""
        if self.build_in:
            alert = self.alerts[0]
            content += f"告警：{alert.title} \n"
            content += f"内容：{alert.content} \n"
            content += f"告警时间:：{alert.format_created_at(self.user_timezone)} \n"
            content += f"负责人:：{','.join(self.username_list)} \n"
        else:
            content += "告警信息如下：\n"
            for index, alert in enumerate(self.alerts[:10]):  # 限制内容展示就是10条
                content += f"{alert.title} {alert.format_created_at(self.user_timezone)} {'.....' if index == 9 else ''} \n"
        return content
