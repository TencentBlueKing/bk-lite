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

    def __init__(self, username_list, channel_id, title, content, append_receivers=True):
        self.title = title
        self.content = content
        self.channel_id = channel_id
        self.append_receivers = append_receivers
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
            receivers=[user["id"] for user in self.user_list],
            append_receivers=self.append_receivers,
        )
        if isinstance(send_result, dict) and send_result.get("result") is False:
            downstream_error_type = send_result.get("error_type")
            if not (
                isinstance(downstream_error_type, str)
                and len(downstream_error_type) <= 64
                and downstream_error_type.isascii()
                and downstream_error_type.replace("_", "").isalnum()
            ):
                downstream_error_type = "ChannelDeliveryRejected"
            logger.warning(
                "event=alert_notification_delivery_failed correlation_id=channel:%s " "channel_id=%s receiver_count=%s failed_stage=%s error_type=%s",
                self.channel_id,
                self.channel_id,
                len(self.user_list),
                "channel_delivery",
                downstream_error_type,
            )
            return send_result
        logger.info(
            "event=alert_notification_delivery_succeeded channel_id=%s receiver_count=%s",
            self.channel_id,
            len(self.user_list),
        )
        return send_result
