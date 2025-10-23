from apps.rpc.base import AppClient, RpcClient


class SystemMgmt(object):
    def __init__(self, is_local_client=False):
        self.client = AppClient("apps.system_mgmt.nats_api") if is_local_client else RpcClient()

    def login(self, username, password):
        """
        :param username: 用户名
        :param password: 密码
        """
        return_data = self.client.run("login", username=username, password=password)
        return return_data

    def verify_bk_token(self, bk_token):
        return_data = self.client.run("verify_bk_token", bk_token=bk_token)
        return return_data

    def wechat_user_register(self, user_id, nick_name):
        """
        :param user_id: 用户ID
        :param nick_name: 昵称
        """
        return_data = self.client.run("wechat_user_register", user_id=user_id, nick_name=nick_name)
        return return_data

    def get_wechat_settings(self):
        return_data = self.client.run("get_wechat_settings")
        return return_data

    def verify_otp_code(self, username, otp_code):
        return_data = self.client.run("verify_otp_code", username=username, otp_code=otp_code)
        return return_data

    def generate_qr_code(self, username):
        return_data = self.client.run("generate_qr_code", username=username)
        return return_data

    def reset_pwd(self, username, password):
        """
        :param username: 用户名
        :param password: 密码
        """
        return_data = self.client.run("reset_pwd", username=username, password=password)
        return return_data

    def get_client(self, client_id, username="", domain="domain.com"):
        return_data = self.client.run("get_client", client_id=client_id, username=username, domain=domain)
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
        return_data = self.client.run("get_user_menus", client_id=client_id, roles=roles, username=username, is_superuser=is_superuser)
        return return_data

    def verify_token(self, token):
        """
        :param token: 用户登录的token
        :param client_id: 当前APP的ID
        """
        return_data = self.client.run("verify_token", token=token)
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
        :param query_params: {"search": ""}
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
        :param receivers: [1,2,3,4] 用户的ID列表
        """
        return_data = self.client.run("send_msg_with_channel", channel_id=channel_id, title=title, content=content, receivers=receivers)
        return return_data

    def init_user_default_attributes(self, user_id, group_name, default_group_id):
        """
        :param user_id: 用户id
        :param group_name: 组名
        :param default_group_id: 默认组ID
        """
        return_data = self.client.run("init_user_default_attributes", user_id=user_id, group_name=group_name, default_group_id=default_group_id)
        return return_data

    def get_user_rules(self, group_id, username):
        """
        :param group_id: 组ID
        :param username: 用户名
        """
        return_data = self.client.run("get_user_rules", group_id=group_id, username=username)
        return return_data

    def get_group_id(self, group_name):
        """
        :param group_name: 组名
        """
        return_data = self.client.run("get_group_id", group_name=group_name)
        return return_data

    def create_default_rule(self, llm_model, ocr_model, embed_model, rerank_model):
        return_data = self.client.run(
            "create_default_rule",
            llm_model=llm_model,
            ocr_model=ocr_model,
            embed_model=embed_model,
            rerank_model=rerank_model,
        )
        return return_data

    def create_guest_role(self):
        return_data = self.client.run("create_guest_role")
        return return_data

    def get_namespace_by_domain(self, domain):
        return_data = self.client.run("get_namespace_by_domain", domain=domain)
        return return_data

    def bk_lite_user_login(self, username, domain):
        return_data = self.client.run("bk_lite_user_login", username=username, domain=domain)
        return return_data

    def get_login_module_domain_list(self):
        return self.client.run("get_login_module_domain_list")

    def get_user_rules_by_app(self, group_id, username, app, module, child_module="", domain="domain.com", include_children=False):
        return self.client.run("get_user_rules_by_app", group_id, username, domain, app, module, child_module, include_children)

    def get_user_rules_by_module(self, group_id, username, app, module, domain="domain.com", include_children=False):
        return self.client.run("get_user_rules_by_module", group_id, username, domain, app, module, include_children)

    def get_pilot_permission_by_token(self, token, bot_id, group_list):
        return self.client.run("get_pilot_permission_by_token", token, bot_id, group_list)

    def delete_rules(self, group_ids, instance_id, app, module, child_module=""):
        return self.client.run("delete_rules", group_ids, instance_id, app, module, child_module)
