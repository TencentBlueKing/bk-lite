from apps.rpc.base import RpcClient


class SystemMgmt(object):
    def __init__(self):
        self.client = RpcClient("system_mgmt")

    def get_client(self, client_id):
        return_data = self.client.run("get_client", client_id)
        return return_data

    def get_client_detail(self, client_id):
        """
        :param client_id: 客户端的ID
        """
        return_data = self.client.run("get_client_detail", client_id)
        return return_data

    def get_user_menus(self, client_id, roles, username, is_superuser):
        """
        :param client_id: 客户端的ID
        :param roles: 查询用户的角色ID列表
        :param username: 查询用户的用户名
        :param is_superuser: 是否超管
        """
        return_data = self.client.run(
            "get_user_menus", client_id=client_id, roles=roles, username=username, is_superuser=is_superuser
        )
        return return_data

    def verify_token(self, token, client_id):
        """
        :param token: 用户登录的token
        :param client_id: 当前APP的ID
        """
        return_data = self.client.run("verify_token", token=token, client_id=client_id)
        return return_data

    def get_group_users(self, group):
        """
        :param group: 当前组的ID
        """
        return_data = self.client.run("get_group_users", group=group)
        return return_data

    def get_all_users(self):
        return_data = self.client.run("get_all_users")
        return return_data

    def search_groups(self, query_params):
        """
        :param query_params: {"page_size": 10, "page": 1, "search": ""}
        """
        return_data = self.client.run("search_groups", query_params=query_params)
        return return_data

    def search_users(self, query_params):
        """
        :param query_params: {"page_size": 10, "page": 1, "search": ""}
        """
        return_data = self.client.run("search_users", query_params=query_params)
        return return_data

    def get_all_groups(self):
        return_data = self.client.run("get_all_groups")
        return return_data

    def search_channel_list(self, channel_type):
        """
        :param channel_type: str， 目前只有email、enterprise_wechat
        """
        return_data = self.client.run("search_channel_list", channel_type=channel_type)
        return return_data

    def send_msg_with_channel(self, channel_id, title, content, receivers):
        """
        :param channel_id: 1 通道id
        :param title: 邮件主题  企微传空字符串即可
        :param content: 正文
        :param receivers: ["abc@canway.net"] 企微传用户的ID列表
        """
        return_data = self.client.run(
            "send_msg_with_channel", channel_id=channel_id, title=title, content=content, receivers=receivers
        )
        return return_data

    def init_user_default_attributes(self, user_id, group_name, default_group_id):
        """
        :param user_id: 用户id
        :param group_name: 组名
        :param default_group_id: 默认组ID
        """
        return_data = self.client.run(
            "init_user_default_attributes", user_id=user_id, group_name=group_name, default_group_id=default_group_id
        )
        return return_data

    def get_user_rules(self, app, group_id, username):
        """
        :param app: 应用
        :param group_id: 组ID
        :param username: 用户名
        """
        return_data = self.client.run("get_user_rules", app=app, group_id=group_id, username=username)
        return return_data

    def get_group_id(self, group_name):
        """
        :param group_name: 组名
        """
        return_data = self.client.run("get_group_id", group_name=group_name)
        return return_data
