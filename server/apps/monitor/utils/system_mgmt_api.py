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
    def send_msg_with_channel(channel_id, title, content, receivers):
        result = SystemMgmt().send_msg_with_channel(channel_id, title, content, receivers)
        return result
