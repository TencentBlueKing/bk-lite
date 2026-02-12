import os

from apps.rpc.base import RpcClient, AppClient


class OpsPilot(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = (
            AppClient("apps.opspilot.nats_api") if is_local_client else RpcClient()
        )

    def get_module_data(self, **kwargs):
        """
        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return_data = self.client.run("get_opspilot_module_data", **kwargs)
        return return_data

    def get_module_list(self):
        return_data = self.client.run("get_opspilot_module_list")
        return return_data

    def get_guest_provider(self, group_id):
        return self.client.run("get_guest_provider", group_id=group_id)
