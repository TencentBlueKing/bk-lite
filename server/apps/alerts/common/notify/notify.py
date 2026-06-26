# -- coding: utf-8 --
# @File: notify.py
# @Time: 2025/6/11 14:06
# @Author: windyzhao
from apps.alerts.utils.system_mgmt_util import SystemMgmtUtils
from apps.core.logger import alert_logger as logger


class Notify:
    """
    Notify class for handling alert notifications.
    This class should be extended by specific notification handlers.
    """

    def __init__(self, username_list, channel_id, title, content):
        self.title = title
        self.content = content
        self.channel_id = channel_id
        self.user_list = self.get_user_list(username_list)

    @staticmethod
    def get_user_list(username_list):
        """
        Get the list of users to notify.
        This method should be implemented by subclasses if needed.
        """
        result = []
        all_users = SystemMgmtUtils.get_user_all()
        user_map = {i["username"]: i for i in all_users}
        for username in username_list:
            user_info = user_map.get(username)
            if user_info:
                result.append(user_info)
        return result

    def get_user_emails(self):
        emails = [user["email"] for user in self.user_list]
        return emails

    def notify(self):

        send_result = SystemMgmtUtils.send_msg_with_channel(
            channel_id=self.channel_id,
            title=self.title,
            content=self.content,
            receivers=[user["id"] for user in self.user_list]
        )
        logger.info(
            "[AlertNotify] 通知已发送: channel_id=%s, content=%s, 下游返回=%s",
            self.channel_id, self.content, send_result,
        )
        return send_result
