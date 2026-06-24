from apps.rpc.system_mgmt import SystemMgmt


class SystemMgmtUtils:

    @staticmethod
    def get_user_all():
        result = SystemMgmt().get_all_users()
        return result["data"]

    @staticmethod
    def search_channel_list(channel_type=""):
        """email、enterprise_wechat"""
        result = SystemMgmt().search_channel_list(channel_type)
        return result["data"]

    @staticmethod
    def search_opspilot_nats_channels(teams=None, bot_id=None, include_children=False):
        """查询 OpsPilot 托管的 NATS 触发通道（config.source == "opspilot"）。"""
        result = SystemMgmt().search_opspilot_nats_channels(
            teams=teams, bot_id=bot_id, include_children=include_children
        )
        return result["data"]

    @staticmethod
    def send_msg_with_channel(channel_id, title, content, receivers):
        result = SystemMgmt().send_msg_with_channel(channel_id, title, content, receivers)
        return result
