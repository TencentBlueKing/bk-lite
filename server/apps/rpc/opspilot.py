from apps.rpc.base import RpcClient


class OpsPilot(object):
    def __init__(self):
        self.client = RpcClient("opspilot")

    def init_user_set(self, group_id, group_name):
        """
        :param group_id: 组ID
        :param group_name: 组名
        """
        return_data = self.client.run("init_user_set", group_id=group_id, group_name=group_name)
        return return_data

    def get_module_data(self, **kwargs):
        """
        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return_data = self.client.run("get_module_data", **kwargs)
        return return_data
